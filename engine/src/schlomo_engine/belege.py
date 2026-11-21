"""pruefe_belege (ADR 0001): every number, test name and code in a draft stands in its cited input; source pointers
resolve; categories equal the engine derivation; procedure blocks come from the catalogue unchanged; D1 for SPF.
Also renders a draft into section texts and result tables for the DOCX export."""
import re

from . import derive, rules
from .config import Config

NUMBER = re.compile(r"\d+(?:[.,]\d+)?")
# A school psychologist recommends the SPF, the education authority decides; "festgestellt" claims a decision
# (Nachtrag 1, Gutachtenstruktur, Empfehlung).
SPF_BEGRIFF = re.compile(r"\bSPF\b|sonderpädagogische\w*\s+Förderbedarf", re.IGNORECASE)
FESTGESTELLT = re.compile(r"\bfestgestellt\b|\bstell(?:t|en)\b[^.]{0,80}\bfest\b|\bFeststellung\b", re.IGNORECASE)


_INDEX = re.compile(r"0|[1-9][0-9]*")


def resolve(doc, pointer: str):
    """JSON pointer (RFC 6901) into doc; raises KeyError if it is malformed or does not resolve. "" is the whole
    document, "/" the member with the empty name (EGM E56)."""
    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
        raise KeyError(pointer)
    node = doc
    for raw in pointer.split("/")[1:]:
        key = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            if not _INDEX.fullmatch(key) or int(key) >= len(node):
                raise KeyError(pointer)
            node = node[int(key)]
        elif isinstance(node, dict) and key in node:
            node = node[key]
        else:
            raise KeyError(pointer)
    return node


def _flatten(node) -> str:
    if isinstance(node, dict):
        return " ".join(_flatten(v) for v in node.values())
    if isinstance(node, list):
        return " ".join(_flatten(v) for v in node)
    return str(node)


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in NUMBER.findall(text)}


def pruefe_belege(output: dict, gi: dict, cfg: Config) -> list[dict]:
    """Returns problems as {feld, problem}; an empty list means every statement is backed by the input."""
    problems = []
    catalogue_names = {e["name"] for e in (cfg.testkatalog or {}).get("eintraege", [])}
    used_names = {t["verfahren"] for t in gi.get("testergebnisse", [])}
    allowed_codes = {rules.icd_norm(gi["gutachten_diagnose"]["icd10_code"])}         if gi.get("gutachten_diagnose", {}).get("icd10_code") else set()
    texts = []
    q1 = "klinische_psychologin" in gi.get("verfasserin", {}).get("qualifikationen", [])
    for a_i, a in enumerate(output["abschnitte"]):
        if a["abschnitt_id"] == "diagnose":  # schema description: never in spf, otherwise only with Q1
            if output["gutachtentyp"] == "spf":
                problems.append({"feld": f"/abschnitte/{a_i}", "problem": "diagnose_im_spf"})
            elif not q1:
                problems.append({"feld": f"/abschnitte/{a_i}", "problem": "diagnose_ohne_q1"})
        for p_i, absatz in enumerate(a.get("absaetze", [])):
            for s_i, satz in enumerate(absatz["saetze"]):
                where = f"/abschnitte/{a_i}/absaetze/{p_i}/saetze/{s_i}"
                if "luecke" in satz:
                    # A gap hint is free text from Claude: no number, no code, no foreign procedure (EGM E05)
                    hint = satz["luecke"]["hinweis"]
                    if _numbers(hint):
                        problems.append({"feld": where, "problem": "zahl_in_luecke"})
                    if rules.ICD_CODE.search(hint):
                        problems.append({"feld": where, "problem": "code_nicht_im_input"})
                    if any(name in hint for name in catalogue_names):
                        problems.append({"feld": where, "problem": "verfahren_in_luecke"})
                    texts.append((where, hint))
                    continue
                sources = []
                for q in satz["quellen"]:
                    try:
                        sources.append(_flatten(resolve(gi, q)))
                    except KeyError:
                        problems.append({"feld": where, "problem": "quelle_unbekannt"})
                backing = " ".join(sources)
                if _numbers(satz["text"]) - _numbers(backing):
                    problems.append({"feld": where, "problem": "zahl_ohne_beleg"})
                for name in catalogue_names - used_names:
                    if name in satz["text"]:
                        problems.append({"feld": where, "problem": "verfahren_nicht_im_input"})
                for code in rules.ICD_CODE.findall(satz["text"]):
                    if rules.icd_norm(code) not in allowed_codes:
                        problems.append({"feld": where, "problem": "code_nicht_im_input"})
                if output["gutachtentyp"] == "spf" and SPF_BEGRIFF.search(satz["text"])                         and FESTGESTELLT.search(satz["text"]):
                    problems.append({"feld": where, "problem": "festgestellt_statt_empfohlen"})
                texts.append((where, satz["text"]))
        for t_i, tabelle in enumerate(a.get("tabellen", [])):
            where = f"/abschnitte/{a_i}/tabellen/{t_i}"
            test = next((t for t in gi.get("testergebnisse", []) if t["testergebnis_id"] == tabelle["testergebnis_id"]), None)
            if test is None:
                problems.append({"feld": where, "problem": "testergebnis_unbekannt"})
                continue
            if tabelle["baustein_quelle"] != test.get("testkatalog_id"):
                problems.append({"feld": where, "problem": "baustein_fremd"})
            t_i_gi = gi["testergebnisse"].index(test)
            for z_i, zeile in enumerate(tabelle["zeilen"]):
                # the value must belong to this table's test, and the row label to that value (EGM E29)
                if not zeile["wert_quelle"].startswith(f"/testergebnisse/{t_i_gi}/werte/"):
                    problems.append({"feld": f"{where}/zeilen/{z_i}", "problem": "quelle_fremd"})
                    continue
                try:
                    # wert_quelle points at an entry of testergebnisse[].werte (contracts/tests: /testergebnisse/0/werte/0)
                    entry = resolve(gi, zeile["wert_quelle"])
                    wert, skala = entry["wert"], entry["skala"]
                    if entry.get("kennung", zeile["kennung"]) != zeile["kennung"]:
                        problems.append({"feld": f"{where}/zeilen/{z_i}", "problem": "kennung_abweichend"})
                except (KeyError, TypeError):
                    problems.append({"feld": f"{where}/zeilen/{z_i}", "problem": "quelle_unbekannt"})
                    continue
                expected = derive.category(cfg, wert, skala, test.get("testkatalog_id"))
                if zeile.get("kategorie") != expected.get("kategorie"):
                    problems.append({"feld": f"{where}/zeilen/{z_i}", "problem": "kategorie_abweichend"})
    if output["gutachtentyp"] == "spf":
        d1 = next((r for r in cfg.rules_for("spf") if r["regel_id"] == "d1"), {"parameter": {}})
        result = rules.d1_texts(texts, d1)[0]
        if result["ergebnis"] == "nicht_erfuellt":
            problems += [{"feld": f, "problem": "diagnose_im_spf"} for f in result["felder"]]
    return problems


def render(output: dict, gi: dict, cfg: Config) -> tuple[dict[str, str], dict[str, list]]:
    """Section texts (gaps visible as [Lücke: ...]) and result tables with the fixed procedure block first."""
    sections, tables = {}, {}
    for a in output["abschnitte"]:
        paragraphs = []
        for absatz in a.get("absaetze", []):
            paragraphs.append(" ".join(s["text"] if "text" in s else f"[Lücke: {s['luecke']['hinweis']}]"
                                       for s in absatz["saetze"]))
        for tabelle in a.get("tabellen", []):
            entry = cfg.test(tabelle["baustein_quelle"])
            paragraphs.append(entry["beschreibungsbaustein"]["text"] if entry else "[Lücke: Verfahrensbaustein fehlt]")
            inhalte = {s["kennung"]: s["inhalte_text"] for i in (entry or {}).get("indizes", []) for s in i["subtests"]}
            rows = [["Index oder Subtest", "Inhalte", "Ergebnis"]]
            rows += [[z["kennung"], inhalte.get(z["kennung"], ""), z.get("kategorie") or "Lücke: Kategorie nicht ableitbar"]
                     for z in tabelle["zeilen"]]
            tables.setdefault(a["abschnitt_id"], []).append(rows)
        sections[a["abschnitt_id"]] = "\n".join(paragraphs)
    return sections, tables
