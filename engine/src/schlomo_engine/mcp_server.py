"""Start type mcp: MCP server for Claude (docs/listen.md, MCP-Tools der Engine). Only anonymised, approved data;
no import, OCR or recognition modules (ADR 0001). Errors carry only a code. The internal diagnosis is never
returned: it is not part of gutachten_input and no tool reads it. speichere_protokoll follows in Task 3, the
Task-5 tools in Task 5."""
import functools

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from . import belege, config, packages, rules, store
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


@mcp.tool()
@_codes
def hole_pruefpaket(session_id: str, rolle: str) -> dict:
    """Exactly the fields allowed for the reviewer role: stil, goldfisch (question and result only) or elefant."""
    art = {"stil": "pruefung_stil", "goldfisch": "pruefung_goldfisch", "elefant": "pruefung_elefant"}.get(rolle)
    if art is None:
        raise EngineError("E_SCHEMA", "argumente")
    return _inhalt(session_id, art)


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
    draft = entwurf or (record.get("entwuerfe") or [None])[-1]
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
    neue = packages.check_befunde(befunde, rolle, record.get("gutachten_input"), config.load())
    record.setdefault("befunde", []).extend(neue)
    store.save(record)
    return {"befunde": len(neue)}


@mcp.tool()
@_codes
def hole_stilprofil() -> dict:
    """The released style profile with short phrasing examples."""
    profil = packages.released_stilprofil()
    if profil is None:
        raise EngineError("E_NICHT_GEFUNDEN")
    return profil


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


# shortcut: wraps the private ToolManager._tools of mcp 2.3.0; recheck when mcp is upgraded (test_step_1_7 covers it).
for _tool in mcp._tool_manager._tools.values():
    object.__setattr__(_tool, "fn_metadata", _CodeOnlyArguments(_tool.fn_metadata))


def serve() -> None:
    mcp.run()
