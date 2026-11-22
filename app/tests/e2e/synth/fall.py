"""Stand-in for Claude in the app e2e tests (herkunft: synthetisch). Runs in a separate process on the same data folder as
the development bridge, like the Code-Tab's `engine mcp` does.

  python fall.py vorlage <basis>                        synthetic SPF template (imported, mapped), Goldfisch criteria
  python fall.py codetab <basis> <session_id>           saves draft and findings through the MCP tools
  python fall.py antwort <basis> <session_id> <paket>   prints the chat answer (one json code block) for a package file
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "engine" / "src"), str(ROOT / "engine" / "tests")]


def _env(basis: Path) -> None:
    os.environ.update({"SCHLOMO_DATA_DIR": str(basis / "daten"),
                       "SCHLOMO_KONFIGURATION": str(basis / "konfiguration"),
                       "SCHLOMO_WISSENSBASIS": str(basis / "wissensbasis"),
                       "SCHLOMO_VORLAGEN": str(basis / "wissensbasis" / "vorlagen")})
    os.chdir(basis / "arbeit")


def entwurf(sid: str, gi: dict) -> dict:
    from schlomo_engine import config, rules
    return {"schema_version": "3", "session_id": sid, "gutachtentyp": "spf", "vorlage_id": "spf-syn", "entwurf_version": 1,
            "regelergebnis": rules.fuer_claude(rules.pruefe_fachregeln(gi, config.load())), "platzhalter": ["name_kind"],
            "abschnitte": [
                {"abschnitt_id": "vorstellungsgrund", "absaetze": [{"absatz_id": "a1", "saetze": [
                    {"text": "[synthetisch] Vorgestellt wegen langsamer Lernfortschritte.", "quellen": ["/vorstellungsgrund"]}]}]},
                {"abschnitt_id": "anamnese", "absaetze": [{"absatz_id": "a2", "saetze": [
                    {"luecke": {"feld": "/anamnese", "hinweis": "keine Anamnese eingegeben"}}]}]},
                {"abschnitt_id": "testbefunde", "tabellen": [{"testergebnis_id": "t1", "baustein_quelle": "iq-test-a", "zeilen": [
                    {"kennung": "I1", "wert_quelle": "/testergebnisse/0/werte/0", "kategorie": "Kategorie C-spezifisch"}]}]},
                {"abschnitt_id": "leistungsproben", "absaetze": [{"absatz_id": "a4", "saetze": [
                    {"text": "[synthetisch] Die Leistungsproben liegen unter der Klassenstufe.", "quellen": ["/leistungsproben"]}]}]},
                {"abschnitt_id": "empfehlung", "absaetze": [{"absatz_id": "a3", "saetze": [
                    {"text": "[synthetisch] Ein sonderpädagogischer Förderbedarf wird empfohlen.", "quellen": ["/empfehlung"]}]}]}]}


def rubberduck_staende(modus: str, sid: str) -> list[dict]:
    """Synthetic protocol states up to abschluss, with one hint as the skill writes it (wording from the config)."""
    from schlomo_engine import rubberduck
    hinweis = [{"art": "kindeswohl", "text": rubberduck.vorgaben()["hinweise"]["kindeswohl"]}]
    if modus == "intervision":
        base = {"schema_version": "1", "session_id": sid, "rollen": {"fallerzaehlerin": "psychologin", "moderation": "ki",
                "berater": [{"berater_id": "b1", "perspektive": "Mehrsprachigkeit und DaZ"}]}}
        sp = {"spontanerzaehlung": {"zusammenfassung": "[synthetisch] Ein Kind der zweiten Stufe zieht sich zurück."}}
        sf = {"schluesselfrage": {"endgueltig": "[synthetisch] Wie gewinne ich die Eltern?", "bestaetigt": True}}
        ber = {"methode": "resonanzrunde", "beratung": [{"runde": 1, "berater_id": "b1", "beitrag": "[synthetisch] Erstsprache ansprechen."}]}
        return [base | {"phase": "rollen"}, base | {"phase": "spontanerzaehlung"} | sp,
                base | {"phase": "schluesselfrage"} | sp | sf, base | {"phase": "methodenwahl", "methode": "resonanzrunde"} | sp | sf,
                base | {"phase": "beratung", "hinweise": hinweis} | sp | sf | ber,
                base | {"phase": "abschluss", "hinweise": hinweis, "abschluss": {"mitnahme": "[synthetisch] Elterngespräch vorbereiten"}} | sp | sf | ber]
    base = {"schema_version": "1", "session_id": sid, "status": "laufend", "ki_kennzeichnung": True, "haltung_version": "von Claude",
            "anliegen": "[synthetisch] Ich fühle mich unter Druck gesetzt."}
    eb = {"ebenen": [{"ebene": "beziehung", "hypothesen": ["[synthetisch] h1"]}]}
    return [base | {"phase": "anliegen"}, base | {"phase": "klaerung"} | eb, base | {"phase": "bearbeitung", "hinweise": hinweis} | eb,
            base | {"phase": "integration", "hinweise": hinweis} | eb,
            base | {"phase": "abschluss", "hinweise": hinweis, "abschluss": {"mitnahme": "[synthetisch] Grenzen benennen"}} | eb]


BEFUND = {"stelle": {"abschnitt_id": "empfehlung", "absatz_id": "a3"}, "problem": "[synthetisch] Beispielbefund",
          "schwere": "mittel", "begruendung": "[synthetisch] Begründung", "entscheidung": {"status": "offen"}}


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # -I ignores PYTHONIOENCODING
    basis = Path(argv[1])
    _env(basis)
    if argv[0] == "vorlage":
        import synth_template as st
        from schlomo_engine import ui_functions as uf
        path = basis / "Vorlage SPF.docx"
        if path.exists():  # already imported in this run
            return 0
        st.build(path)
        uf.vorlage_zuordnen({"vorlage": st.vorlage(uf.vorlage_importieren({"pfad": str(path)})["datei"])})
        # synthetic Goldfisch criteria from the reviewer eval (the real ones are still open)
        (basis / "wissensbasis").mkdir(exist_ok=True)
        (basis / "wissensbasis" / "goldfisch-kriterien.md").write_text(
            (ROOT / "evals" / "pruefer" / "goldfisch-kriterien.md").read_text(encoding="utf-8"), encoding="utf-8")
        return 0
    if argv[0] == "vorlagedatei":  # a second synthetic template file, not imported
        import synth_template as st
        st.build(basis / "Neue Vorlage.docx")
        return 0
    if argv[0] == "verbessern":  # /verbessern in the Code-Tab: three signals, one proposal, the eval suite
        import secrets
        from schlomo_engine import mcp_server as m, store, ui_functions as uf
        sid = uf.sitzung_anlegen({"bezeichnung": "Fall Lernen", "modus": "gutachten", "gutachtentyp": "spf"})["session"]["session_id"]
        record = store.load(sid)
        ids = [f"ls-{secrets.token_hex(4)}" for _ in range(3)]
        record["lernsignale"] = [{"schema_version": "1", "signal_id": i, "herkunft": "gutachten", "art": "befund_verworfen",
                                  "bereich": "sprache", "pruefer": "stil", "konfiguration_version": "keine"} for i in ids]
        store.save(record)
        text = {"gut": "[synthetisch] Fachbegriffe beim ersten Vorkommen in Klammern erklären.",
                "gut2": "[synthetisch] Kurze Hauptsätze bevorzugen.",
                "schlecht": "[synthetisch] Den Förderbedarf als festgestellt formulieren."}[argv[2]]
        v = m.schlage_konfiguration_vor({"datei": "lernbausteine.json", "herkunft": "gutachten", "bereich": "sprache",
                                         "signal_ids": ids, "aenderung": {"art": "hinzufuegen", "ziel": "entwurf", "text": text},
                                         "begruendung": "[synthetisch] dreimal ergänzt"})
        print(m.starte_evals(v["vorschlag_id"])["status"])
        return 0
    sid = argv[2]
    if argv[0] == "eingabe":  # synthetic input with Q1, saved like the app does
        import copy
        from schlomo_engine import ui_functions as uf
        from test_step_1_4 import GI
        uf.bekannte_namen_setzen({"session_id": sid, "namen": []})
        out = uf.eingabe_speichern({"session_id": sid, "gutachten_input": copy.deepcopy(GI) | {"session_id": sid},
                                    "unsichere_bestaetigt": True})
        assert out["gespeichert"], out
        return 0
    from schlomo_engine import mcp_server as m, store
    gi = store.load(sid).get("gutachten_input")
    if argv[0] == "codetab":
        m.speichere_entwurf(sid, entwurf(sid, gi))
        for rolle in ("stil", "goldfisch", "elefant"):
            m.speichere_befunde(sid, rolle, [BEFUND | {"pruefer": rolle, "problem": f"[synthetisch] Befund {rolle}"}])
        return 0
    if argv[0] in ("intervision", "supervision"):  # the Code-Tab runs the session up to abschluss, then the reviews
        from schlomo_engine import rubberduck
        for state in rubberduck_staende(argv[0], sid):
            m.speichere_protokoll(sid, state)
        if argv[0] == "intervision":
            m.speichere_befunde(sid, "elefant", [{"stelle": {"protokoll_phase": "beratung"}, "problem": "[synthetisch] Annahme ohne Beleg",
                                                  "schwere": "mittel", "begruendung": "[synthetisch] nicht in der Erzählung", "pruefer": "elefant"}])
        m.speichere_befunde(sid, "goldfisch", [])
        return 0
    if argv[0] == "stilprofil":  # /stil-lernen in the Code-Tab: always a draft
        m.speichere_stilprofil({"schema_version": "1", "version": "v1", "status": "entwurf", "anzahl_probegutachten": 1,
                                "merkmale": [{"merkmal_id": "m1", "kategorie": "satzbau", "beschreibung": "[synthetisch] Quellen am Satzanfang",
                                              "belegzitate": [{"text": "[synthetisch] Laut Bericht der Schule ...", "probe_id": "pg-00000001"}]}],
                                "formulierungsbeispiele": [{"abschnitt_id": "empfehlung", "text": "[synthetisch] Empfohlen wird ..."}]})
        return 0
    if argv[0] == "diagnose":  # Claude's proposal through the MCP tool, as the subagent diagnosevorschlag does
        m.speichere_diagnosevorschlag(sid, {"schema_version": "1", "session_id": sid, "quelle": "claude", "kriterien": "erfuellt", "icd10_code": "F71",
                                            "begruendung": [{"text": "[synthetisch] Werte im Bereich laut Eingabe.", "quellen": ["/testergebnisse"]}],
                                            "hinweis": "[synthetisch] KI-Vorschlag, die Entscheidung trifft die Psychologin."})
        return 0
    paket = json.loads(Path(argv[3]).read_text(encoding="utf-8"))
    if paket["erwartete_rueckgabe"].startswith("protokoll-"):
        daten = rubberduck_staende(paket["art"], sid)[-1]
    elif paket["art"] in ("protokoll_elefant", "protokoll_goldfisch"):
        daten = []
    elif paket["erwartete_rueckgabe"] == "gutachten-output":
        daten = entwurf(sid, gi)
    else:
        rolle = {"pruefung_stil": "stil", "pruefung_goldfisch": "goldfisch", "pruefung_elefant": "elefant"}[paket["art"]]
        daten = [BEFUND | {"befund_id": "bf-00000000", "pruefer": rolle, "problem": f"[synthetisch] Befund {rolle}"}]
    block = {"schema_version": "2", "paket_id": paket["paket_id"], "typ": paket["erwartete_rueckgabe"], "daten": daten}
    print("Skill aktiv\n```json\n" + json.dumps(block, ensure_ascii=False) + "\n```")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
