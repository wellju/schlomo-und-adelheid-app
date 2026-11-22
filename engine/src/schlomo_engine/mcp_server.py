"""Start type mcp: MCP server for Claude (docs/listen.md, MCP-Tools der Engine). Only anonymised, approved data;
no import, OCR or recognition modules (ADR 0001). Errors carry only a code. The internal diagnosis is never
returned: it is not part of gutachten_input and no tool reads it. The Task-5 tools follow in Task 5."""
import functools

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from . import belege, config, packages, rubberduck, rules, store
from .contracts import validate
from .errors import EngineError
from .logging_safe import log

mcp = MCPServer("schlomo-engine")


def _codes(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            for attempt in range(3):  # every tool reloads the record, so a retry after a write conflict is safe
                try:
                    return func(*args, **kwargs)
                except EngineError as e:
                    if e.reason != "konflikt" or attempt == 2:
                        raise
        except EngineError as e:
            log("mcp_fehler", code=e.code)
            raise ToolError(e.code) from None
        except ToolError:
            raise
        except Exception:  # never leak exception text
            log("mcp_fehler", code="E_INTERN")
            raise ToolError("E_INTERN") from None
    return wrapper


def _record(session_id: str) -> dict:
    return store.load(session_id)


def _inhalt(session_id: str, art: str) -> dict:
    """Package contents for Claude, validated against fallpaket.schema.json like the browser path (EGM E35)."""
    return packages.make_package(_record(session_id), art, config.load(), {})["inhalt"]


@mcp.tool()
@_codes
def liste_sitzungen() -> list[dict]:
    """List sessions with neutral label, mode and status. No documents, no inputs, no diagnosis."""
    return [{k: r["session"][k] for k in ("session_id", "bezeichnung", "modus", "status")}
            for r in store.all_records()]


@mcp.tool()
@_codes
def hole_gutachten_input(session_id: str) -> dict:
    """Input, rule result (fuer_claude), template without file name, categories and fixed procedure blocks."""
    return _inhalt(session_id, "gutachten")


# One tool per reviewer with a fixed role: a subagent's tools list then limits the data it can reach, not only
# its prompt (EGM Task 2 E01; ADR 0001, enforcement in code).
@mcp.tool()
@_codes
def hole_goldfisch_paket(session_id: str) -> dict:
    """Only question and result text plus the criteria, for the Goldfisch."""
    return _inhalt(session_id, "pruefung_goldfisch")


@mcp.tool()
@_codes
def hole_stil_paket(session_id: str) -> dict:
    """Draft and released style profile (without sample quotes), for the style review."""
    return _inhalt(session_id, "pruefung_stil")


@mcp.tool()
@_codes
def hole_elefant_paket(session_id: str) -> dict:
    """Input, draft, rule result (fuer_claude), categories and blocks, for the Elefant."""
    return _inhalt(session_id, "pruefung_elefant")


@mcp.tool()
@_codes
def hole_diagnose_paket(session_id: str) -> dict:
    """Only with Q1: input without the psychologist's diagnosis and without draft, for the blind comparison."""
    return _inhalt(session_id, "diagnosevorschlag")


@mcp.tool()
@_codes
def pruefe_fachregeln(session_id: str) -> dict:
    """Deterministic rule check against rule set and test catalogue; only the form fuer_claude."""
    record = _record(session_id)
    if "gutachten_input" not in record:
        raise EngineError("E_NICHT_GEFUNDEN")
    result = rules.fuer_claude(rules.pruefe_fachregeln(record["gutachten_input"], config.load()))
    validate("regelergebnis", result, "fuer_claude")
    return result


@mcp.tool()
@_codes
def pruefe_belege(session_id: str, entwurf: dict | None = None) -> list[dict]:
    """Every number, test name and code in the draft must stand in the input; every source pointer must resolve.
    Without a draft argument the current draft is checked."""
    record = _record(session_id)
    if entwurf is not None:
        # a draft from Claude is checked against the schema first, so a broken one gives E_SCHEMA, not E_INTERN; an
        # empty dict is a draft too and never silently replaced by the stored one (EGM Task 2 E19)
        validate("gutachten-output", entwurf | {"entwurf_version": entwurf.get("entwurf_version", 1)})
        draft = entwurf
    else:
        draft = (record.get("entwuerfe") or [None])[-1]
    if draft is None or "gutachten_input" not in record:
        raise EngineError("E_NICHT_GEFUNDEN")
    return belege.pruefe_belege(draft, record["gutachten_input"], config.load())


@mcp.tool()
@_codes
def speichere_entwurf(session_id: str, entwurf: dict) -> dict:
    """Store a draft after schema, rule-result and evidence checks as a new version."""
    record = _record(session_id)
    draft = packages.check_draft(entwurf, record, config.load())
    record.setdefault("entwuerfe", []).append(draft)
    store.save(record)
    return {"entwurf_version": draft["entwurf_version"]}


@mcp.tool()
@_codes
def hole_entwurf(session_id: str) -> dict:
    """The current draft."""
    draft = (_record(session_id).get("entwuerfe") or [None])[-1]
    if draft is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    return draft


@mcp.tool()
@_codes
def speichere_befunde(session_id: str, rolle: str, befunde: list[dict]) -> dict:
    """Store review findings; IDs are assigned new, decisions stay open; Elefant findings that contradict the
    rule result are rejected."""
    record = _record(session_id)
    for b in befunde:
        validate("befund", b | {"befund_id": "bf-00000000", "entscheidung": {"status": "offen"}})
    if record["session"]["modus"] != "gutachten":  # review of a protocol, counted even without findings
        rubberduck.check_protokoll_befunde(record, rolle, befunde)
        rubberduck.pruefung_vermerken(record, rolle)
    neue = packages.check_befunde(befunde, rolle, record.get("gutachten_input"), config.load())
    record.setdefault("befunde", []).extend(neue)
    store.save(record)
    return {"befunde": len(neue)}


@mcp.tool()
@_codes
def hole_stilprofil() -> dict:
    """The released style profile: features and short phrasing examples, without sample quotes."""
    profil = packages.released_stilprofil()
    if profil is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    result = packages.stilprofil_fuer_claude(profil)
    validate("stilprofil", result, "fuer_claude")
    return result


@mcp.tool()
@_codes
def hole_probetexte(session_id: str) -> dict:
    """Anonymised, released sample reports of a style-learning session for /stil-lernen."""
    return _inhalt(session_id, "stil_lernen")


@mcp.tool()
@_codes
def speichere_stilprofil(stilprofil: dict) -> dict:
    """Store a style profile, always with status entwurf."""
    profil = packages.save_stilprofil(stilprofil)
    return {"version": profil["version"], "status": "entwurf"}


@mcp.tool()
@_codes
def speichere_diagnosevorschlag(session_id: str, vorschlag: dict) -> dict:
    """Store Claude's diagnosis proposal for the blind comparison (only with Q1). Never returns the internal
    diagnosis."""
    record = _record(session_id)
    record.setdefault("diagnosevorschlaege", []).append(
        packages.check_claude_proposal(vorschlag, record, config.load()))
    store.save(record)
    return {"gespeichert": True}


@mcp.tool()
@_codes
def hole_wissensbasis(name: str) -> str:
    """haltung.md, goldfisch-kriterien.md or a stored guideline, by file name only."""
    return packages.wissen(name)


@mcp.tool()
@_codes
def hole_rubberduck_vorgaben() -> dict:
    """Hint wordings (kindeswohl, akute_gefaehrdung) and adviser perspectives from the configuration, null if missing."""
    return rubberduck.vorgaben()


@mcp.tool()
@_codes
def hole_protokoll(session_id: str) -> dict:
    """Current state of the intervision or supervision protocol of a session."""
    protokoll = rubberduck.current(_record(session_id))
    if protokoll is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    return protokoll


@mcp.tool()
@_codes
def hole_protokoll_goldfisch(session_id: str) -> dict:
    """Only key question or concern, contributions or hypotheses and what the psychologist takes away, for the
    Goldfisch."""
    return rubberduck.goldfisch_sicht(_record(session_id))


@mcp.tool()
@_codes
def speichere_protokoll(session_id: str, protokoll: dict) -> dict:
    """Store a new state of the intervision or supervision protocol. Each save stays in the phase or moves exactly
    one on; content of a later phase (e.g. advice before the method choice) is rejected with E_PHASENFOLGE."""
    record = _record(session_id)
    result = rubberduck.speichere(record, protokoll)
    store.save(record)
    return result


@mcp.tool()
@_codes
def speichere_hypothesenpruefung(session_id: str, vignette: str, schlussfolgerung: str, befunde: list[dict]) -> dict:
    """Store the Goldfisch's findings on a vignette and conclusion (/hypothese-pruefen) in the running protocol."""
    record = _record(session_id)
    result = rubberduck.speichere_hypothese(record, vignette, schlussfolgerung, befunde)
    store.save(record)
    return result


class _CodeOnlyArguments:
    """The SDK reports argument errors with the pydantic text, which repeats the input value (EGM E21). This keeps
    the SDK's validation and replaces only the message by the code."""

    def __init__(self, meta):
        self._meta = meta

    def __getattr__(self, name):
        return getattr(self._meta, name)

    def validate_arguments(self, arguments):
        try:
            return self._meta.validate_arguments(arguments)
        except ValidationError:
            log("mcp_fehler", code="E_SCHEMA")
            raise ValidationError.from_exception_data("E_SCHEMA", []) from None


# ---------------------------------------------------------------- learning loop (Task 5, only /verbessern)

@mcp.tool()
@_codes
def hole_lernsignale() -> dict:
    """Learning signals from reports and intervision (never supervision, never the diagnosis comparison), grouped by
    origin and area, with the signals already used in a proposal marked."""
    from . import lernschleife
    return lernschleife.signale_uebersicht()


@mcp.tool()
@_codes
def schlage_konfiguration_vor(vorschlag: dict) -> dict:
    """Argument: {"vorschlag": {...}}. Propose one change to lernbausteine.json from at least three unused signals of the same origin and area.
    Every other file is locked (rule set, scale, templates, catalogue, wordings, ICD-10, comparison, supervision)."""
    from . import lernschleife
    return lernschleife.schlage_vor(vorschlag)


@mcp.tool()
@_codes
def starte_evals(vorschlag_id: str) -> dict:
    """Run the deterministic eval suite for a proposal; a case that fails with the change rejects it. The release
    happens only in the app."""
    from . import lernschleife
    return lernschleife.starte_evals(vorschlag_id)


# shortcut: wraps the private ToolManager._tools of mcp 2.3.0; after every @mcp.tool() above (EGM Task 5 C6); recheck when mcp is upgraded (test_step_1_7 covers it).
for _tool in mcp._tool_manager._tools.values():
    object.__setattr__(_tool, "fn_metadata", _CodeOnlyArguments(_tool.fn_metadata))


def serve() -> None:
    mcp.run()
