"""Deterministic rule check (ADR 0001, Fachregelprüfung): pure function, no LLM, no network. Rule IDs and effects as
in Nachtrag 1; every threshold comes from the regelwerk parameters. Missing procedure, value or parameter:
"nicht_pruefbar", never "erfuellt"."""
import re

from .config import Config

# Effect per rule ID, fixed by Nachtrag 1 (Regel-IDs) and never overridden by the regelwerk (EGM E33); only rules
# unknown to Nachtrag 1 take "wirkung" from the regelwerk.
WIRKUNG = {"awmf_a": "blockiert_diagnose", "awmf_b": "blockiert_diagnose", "awmf_d": "blockiert_diagnose",
           "awmf_e": "blockiert_diagnose", "awmf_f": "hinweis", "normen_alter": "hinweis", "konfidenz_95": "hinweis",
           "spf_s1": "blockiert_export", "spf_s2": "blockiert_export", "spf_s3": "blockiert_export",
           "q1": "blockiert_export", "d1": "blockiert_export"}
BLOCKING = ("blockiert_diagnose", "blockiert_export")
# Export rules every report of a type needs; missing from the regelwerk they count as nicht_pruefbar (EGM E30).
REQUIRED = {"spf": ("spf_s1", "spf_s2", "spf_s3", "q1", "d1")}
REQUIRED_ALL = ("q1",)
# Upper case with optional space ("F70", "F 70") or lower case without ("f70"); a lower-case letter with a space is
# too common in German text to count as a code.
ICD_CODE = re.compile(r"\b(?:[A-Z]\s?\d{2}|[a-z]\d{2})(?:\.\d{1,2})?\b")


def icd_norm(code: str) -> str:
    return code.replace(" ", "").upper()


def _result(ergebnis, begruendung, felder, testergebnis_id=None):
    r = {"ergebnis": ergebnis, "begruendung": begruendung, "felder": felder}
    if testergebnis_id:
        r["testergebnis_id"] = testergebnis_id
    return r


def _intelligence_tests(gi, cfg):
    for i, t in enumerate(gi.get("testergebnisse", [])):
        entry = cfg.test(t.get("testkatalog_id"))
        if entry and entry["art"] == "intelligenztest":
            yield i, t, entry


def _per_iq_test(gi, cfg, check):
    tests = list(_intelligence_tests(gi, cfg))
    if not tests:
        return [_result("nicht_pruefbar", "kein Intelligenztest aus dem Testkatalog", ["/testergebnisse"])]
    return [check(i, t, entry) for i, t, entry in tests]


def _param(rule, key):
    value = rule.get("parameter", {}).get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def awmf_a(gi, cfg, rule):
    q = gi.get("drei_quellen", {})
    status = [q.get(k) for k in ("klinischer_eindruck", "intelligenztest", "befragung_adaptives_verhalten")]
    if all(s == "dokumentiert" for s in status):
        return [_result("erfuellt", "drei Quellen dokumentiert", ["/drei_quellen"])]
    if "fehlt" in status:
        return [_result("nicht_erfuellt", "mindestens eine der drei Quellen fehlt", ["/drei_quellen"])]
    return [_result("nicht_pruefbar", "Quellenstatus unvollständig", ["/drei_quellen"])]


def awmf_b(gi, cfg, rule):
    limit = _param(rule, "ki_obergrenze_max")

    def check(i, t, entry):
        felder = [f"/testergebnisse/{i}/ki_obergrenze", f"/testergebnisse/{i}/ki_niveau"]
        if limit is None:
            return _result("nicht_pruefbar", "Parameter ki_obergrenze_max fehlt im Regelwerk", felder, t["testergebnis_id"])
        if "ki_obergrenze" not in t or "ki_niveau" not in t:
            return _result("nicht_pruefbar", "Konfidenzintervall oder Niveau fehlt", felder, t["testergebnis_id"])
        ok = t["ki_obergrenze"] <= limit
        return _result("erfuellt" if ok else "nicht_erfuellt",
                       f"Obergrenze des Konfidenzintervalls {'höchstens' if ok else 'über'} {limit}", felder,
                       t["testergebnis_id"])
    return _per_iq_test(gi, cfg, check)


def awmf_d(gi, cfg, rule):
    k_min, r_min = _param(rule, "innere_konsistenz_min"), _param(rule, "retest_min")

    def check(i, t, entry):
        felder = [f"/testergebnisse/{i}/testkatalog_id"]
        if k_min is None or r_min is None:
            return _result("nicht_pruefbar", "Parameter für Reliabilität fehlen im Regelwerk", felder, t["testergebnis_id"])
        k, r = entry.get("innere_konsistenz"), entry.get("retest")
        if not k or not r:
            return _result("nicht_pruefbar", "Kennwert im Testkatalog fehlt", felder, t["testergebnis_id"])
        ok = k["wert"] >= k_min and r["wert"] >= r_min
        return _result("erfuellt" if ok else "nicht_erfuellt", "Reliabilität laut Testkatalog", felder,
                       t["testergebnis_id"])
    return _per_iq_test(gi, cfg, check)


def awmf_e(gi, cfg, rule):
    limit = _param(rule, "iq_min_unter")

    def check(i, t, entry):
        felder = [f"/testergebnisse/{i}/einzeltestung", f"/testergebnisse/{i}/testkatalog_id"]
        if limit is None:
            return _result("nicht_pruefbar", "Parameter iq_min_unter fehlt im Regelwerk", felder, t["testergebnis_id"])
        # strictly below: values under the limit (e.g. IQ 60) must be measurable (projektrahmen.md)
        ok = entry["messbereich"]["iq_min"] < limit and t["einzeltestung"] and entry["einzeltestung"]
        return _result("erfuellt" if ok else "nicht_erfuellt", "Messbereich und Einzeltestung", felder,
                       t["testergebnis_id"])
    return _per_iq_test(gi, cfg, check)


def awmf_f(gi, cfg, rule):
    """Severity only as a suggestion; also returns the suggestion for schweregrad_vorschlag."""
    stufen, hinweis = rule.get("parameter", {}).get("stufen"), rule.get("parameter", {}).get("hinweis")
    tests = [(i, t) for i, t, _ in _intelligence_tests(gi, cfg) if "gesamt_iq" in t]
    if not stufen or not hinweis or len(tests) != 1:
        why = "Stufen oder Hinweis fehlen im Regelwerk" if not stufen or not hinweis else \
            "nicht genau ein Gesamt-IQ eines Intelligenztests"
        return [_result("nicht_pruefbar", why, ["/testergebnisse"])]
    i, t = tests[0]
    stufe = next((s for s in stufen if s["von"] <= t["gesamt_iq"] <= s["bis"]), None)
    res = _result("erfuellt" if stufe else "nicht_pruefbar",
                  "Schweregrad als Vorschlag" if stufe else "kein Stufenbereich passt", [f"/testergebnisse/{i}/gesamt_iq"],
                  t["testergebnis_id"])
    res["_vorschlag"] = {"stufe": stufe["stufe"] if stufe else "kein_vorschlag", "hinweis": hinweis,
                         "icd10": stufe.get("icd10") if stufe else None}
    return [res]


def normen_alter(gi, cfg, rule):
    limit = _param(rule, "max_jahre")
    out = []
    for i, t in enumerate(gi.get("testergebnisse", [])):
        felder = [f"/testergebnisse/{i}/normen_alter_jahre"]
        if limit is None or "normen_alter_jahre" not in t:
            out.append(_result("nicht_pruefbar", "Normalter oder Parameter max_jahre fehlt", felder, t["testergebnis_id"]))
        elif t["normen_alter_jahre"] <= limit:
            out.append(_result("erfuellt", f"Normen höchstens {limit} Jahre alt", felder, t["testergebnis_id"]))
        else:
            begruendet = bool(t.get("normen_begruendung", "").strip())
            out.append(_result("nicht_erfuellt", f"Normen älter als {limit} Jahre; Begründung "
                               + ("vorhanden" if begruendet else "fehlt, Lücke im Entwurf"),
                               felder + [f"/testergebnisse/{i}/normen_begruendung"], t["testergebnis_id"]))
    return out or [_result("nicht_pruefbar", "keine Testergebnisse", ["/testergebnisse"])]


def konfidenz_95(gi, cfg, rule):
    """Every result that states a confidence level, not only intelligence tests (Nachtrag 1, EGM E32)."""
    niveau = _param(rule, "niveau")
    out = []
    for i, t in enumerate(gi.get("testergebnisse", [])):
        felder = [f"/testergebnisse/{i}/ki_niveau"]
        if niveau is None or "ki_niveau" not in t:
            out.append(_result("nicht_pruefbar", "Niveau oder Parameter fehlt", felder, t["testergebnis_id"]))
            continue
        ok = abs(t["ki_niveau"] - niveau) < 1e-9
        out.append(_result("erfuellt" if ok else "nicht_erfuellt",
                           f"Konfidenzniveau {'gleich' if ok else 'ungleich'} {niveau}", felder, t["testergebnis_id"]))
    return out or [_result("nicht_pruefbar", "keine Testergebnisse", ["/testergebnisse"])]


def _text_present(obj) -> bool:
    return isinstance(obj, dict) and bool(str(obj.get("text", "")).strip())


def spf_s1(gi, cfg, rule):
    tests = list(_intelligence_tests(gi, cfg))
    if tests and any(t["werte"] for _, t, _ in tests):
        return [_result("erfuellt", "kognitive Ausgangslage mit Testbefund dokumentiert", ["/testergebnisse"])]
    if gi.get("testergebnisse") and not tests:
        return [_result("nicht_pruefbar", "Testergebnisse ohne Intelligenztest aus dem Testkatalog", ["/testergebnisse"])]
    return [_result("nicht_erfuellt", "kein Testbefund zur kognitiven Ausgangslage", ["/testergebnisse"])]


def spf_s2(gi, cfg, rule):
    lp = gi.get("leistungsproben", {})
    ok = _text_present(lp.get("deutsch", {}).get("lesen")) and _text_present(lp.get("deutsch", {}).get("schreiben")) \
        and _text_present(lp.get("mathematik"))
    return [_result("erfuellt" if ok else "nicht_erfuellt", "Leistungsproben Deutsch (Lesen, Schreiben) und Mathematik",
                    ["/leistungsproben"])]


def spf_s3(gi, cfg, rule):
    ok = _text_present(gi.get("foerderung_und_umfeld"))
    return [_result("erfuellt" if ok else "nicht_erfuellt", "personen- und umweltbezogene Faktoren, bisherige Förderung",
                    ["/foerderung_und_umfeld"])]


def q1(gi, cfg, rule):
    ok = "klinische_psychologin" in gi.get("verfasserin", {}).get("qualifikationen", [])
    if "gutachten_diagnose" not in gi:
        # A diagnosis may also be written into another field; an ICD code there needs Q1 as well (EGM E52).
        codes = [p for p, text in input_texts(gi) if ICD_CODE.search(text)]
        if codes and not ok:
            return [_result("nicht_erfuellt", "ICD-Code im Input ohne Qualifikation klinische Psychologin",
                            ["/verfasserin/qualifikationen", *codes])]
        return [_result("erfuellt", "keine Diagnose im Gutachten", ["/gutachten_diagnose"])]
    return [_result("erfuellt" if ok else "nicht_erfuellt", "Diagnose nur mit Qualifikation klinische Psychologin",
                    ["/verfasserin/qualifikationen", "/gutachten_diagnose"])]


def d1_texts(texts: list[tuple[str, str]], rule) -> list[dict]:
    """D1 on (pointer, text) pairs: no ICD code, no term from the psychologist's list. Reused for drafts in 1.5."""
    hits = [p for p, text in texts if ICD_CODE.search(text)]
    begriffe = rule.get("parameter", {}).get("begriffe")
    if isinstance(begriffe, list) and begriffe:
        hits += [p for p, text in texts if any(re.search(rf"(?<!\w){re.escape(b)}", text, re.I) for b in begriffe)]
    if hits:
        return [_result("nicht_erfuellt", "ICD-Code oder Diagnosebegriff im Text", sorted(set(hits)))]
    if not (isinstance(begriffe, list) and begriffe):
        return [_result("nicht_pruefbar", "keine ICD-Codes; Begriffsliste fehlt im Regelwerk", ["/"])]
    return [_result("erfuellt", "keine ICD-Codes und keine Diagnosebegriffe", ["/"])]


def input_texts(gi) -> list[tuple[str, str]]:
    out = []

    def walk(node, pointer):
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{pointer}/{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{pointer}/{i}")
        elif isinstance(node, str):
            out.append((pointer, node))
    walk(gi, "")
    return [(p, t) for p, t in out if not p.endswith(("/session_id", "/gutachtentyp", "/vorlage_id"))]


def d1(gi, cfg, rule):
    return d1_texts(input_texts(gi), rule)


RULES = {f.__name__: f for f in (awmf_a, awmf_b, awmf_d, awmf_e, awmf_f, normen_alter, konfidenz_95,
                                 spf_s1, spf_s2, spf_s3, q1, d1)}


def _gesamt(ergebnisse) -> str:
    blocking = [e["ergebnis"] for e in ergebnisse if e["wirkung"] in BLOCKING]
    if "nicht_erfuellt" in blocking:
        return "nicht_erfuellt"
    if "nicht_pruefbar" in blocking or not blocking:
        return "nicht_pruefbar"
    return "erfuellt"


def pruefe_fachregeln(gi: dict, cfg: Config) -> dict:
    ergebnisse, vorschlag = [], None
    for rule in cfg.rules_for(gi["gutachtentyp"]):
        func = RULES.get(rule["regel_id"])
        results = func(gi, cfg, rule) if func else [_result("nicht_pruefbar", "Regel ohne Umsetzung in der Engine", ["/"])]
        for r in results:
            vorschlag = r.pop("_vorschlag", vorschlag)
            ergebnisse.append({"regel_id": rule["regel_id"], "regel_version": rule["version"],
                               "regel_status": "freigegeben" if rule["status"] == "freigegeben" else "entwurf",
                               "wirkung": WIRKUNG.get(rule["regel_id"]) or rule.get("wirkung") or "hinweis", **r})
    present = {r["regel_id"] for r in cfg.rules_for(gi["gutachtentyp"])}
    for rid in (*REQUIRED.get(gi["gutachtentyp"], ()), *REQUIRED_ALL):
        if rid not in present and all(e["regel_id"] != rid for e in ergebnisse):
            ergebnisse.append({"regel_id": rid, "regel_version": "fehlt", "regel_status": "entwurf",
                               "wirkung": WIRKUNG[rid], **_result("nicht_pruefbar", "Regel fehlt im Regelwerk", ["/"])})
    result = {"regelwerk_version": cfg.version("regelwerk"), "testkatalog_version": cfg.version("testkatalog"),
              "ergebnisse": ergebnisse, "gesamt": _gesamt(ergebnisse)}
    if vorschlag:
        result["schweregrad_vorschlag"] = {"stufe": vorschlag["stufe"], "hinweis": vorschlag["hinweis"]}
    return result


def _severity_code(gi: dict, cfg: Config) -> str | None:
    rule = next((r for r in cfg.rules_for(gi["gutachtentyp"]) if r["regel_id"] == "awmf_f"), None)
    return awmf_f(gi, cfg, rule)[0].get("_vorschlag", {}).get("icd10") if rule else None


def fuer_claude(regelergebnis: dict) -> dict:
    """The only form Claude sees: no awmf_* results, no severity; gesamt recomputed without them (Nachtrag 1)."""
    ergebnisse = [e for e in regelergebnis["ergebnisse"] if not e["regel_id"].startswith("awmf_")]
    return {"regelwerk_version": regelergebnis["regelwerk_version"],
            "testkatalog_version": regelergebnis["testkatalog_version"],
            "ergebnisse": ergebnisse, "gesamt": _gesamt(ergebnisse)}


def engine_diagnosevorschlag(gi: dict, regelergebnis: dict, cfg: Config) -> dict:
    """Engine proposal for the blind comparison (Nachtrag 1, Diagnosevergleich): criteria from awmf_a, awmf_b, awmf_d
    and awmf_e; awmf_f only adds the severity and its reasoning. An ICD code is taken only if it exists in the local
    reference data."""
    by_id = {}
    for e in regelergebnis["ergebnisse"]:
        by_id.setdefault(e["regel_id"], []).append(e)
    needed = [e["ergebnis"] for rid in ("awmf_a", "awmf_b", "awmf_d", "awmf_e") for e in by_id.get(rid, [])]
    kriterien = "nicht_erfuellt" if "nicht_erfuellt" in needed else \
        "erfuellt" if needed and all(r == "erfuellt" for r in needed) and len({*by_id} & {"awmf_a", "awmf_b", "awmf_d", "awmf_e"}) == 4 \
        else "nicht_pruefbar"
    begruendung = [{"text": f"{e['regel_id']}: {e['begruendung']}", "quellen": e["felder"]}
                   for rid in ("awmf_a", "awmf_b", "awmf_d", "awmf_e", "awmf_f") for e in by_id.get(rid, [])]
    vorschlag = regelergebnis.get("schweregrad_vorschlag")
    hinweis = vorschlag["hinweis"] if vorschlag else "Kein Schweregrad-Vorschlag möglich."
    out = {"schema_version": "1", "session_id": gi["session_id"], "quelle": "engine", "kriterien": kriterien,
           "begruendung": begruendung, "hinweis": hinweis, "regelergebnis_version": regelergebnis["regelwerk_version"]}
    if vorschlag and kriterien == "erfuellt":
        out["schweregrad_vorschlag"] = vorschlag["stufe"]
        code = _severity_code(gi, cfg)
        if code and cfg.icd_exists(code):
            out["icd10_code"] = code
        elif code:
            out["hinweis"] += " ICD-Code nicht in den lokalen Referenzdaten, daher nicht übernommen."
    return out
