"""Schema check for contracts/. Synthetic data only.

Usage: python -I contracts/tests/check_contracts.py contracts
Expected: last line "<n> Schemas gueltig, <m> Pruefungen bestanden", exit code 0. Any failure: exit code 1.
Requires: jsonschema>=4.18 (with referencing).
"""
import json
import pathlib
import sys

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

if len(sys.argv) != 2 or not pathlib.Path(sys.argv[1]).is_dir():
    print("Aufruf: python -I contracts/tests/check_contracts.py contracts")
    sys.exit(1)

d = pathlib.Path(sys.argv[1])
schemas = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.schema.json"))}
failures = []
for name, s in schemas.items():
    Draft202012Validator.check_schema(s)
    if s.get("$id") != name:
        failures.append(f"$id passt nicht zum Dateinamen: {name}")
reg = Registry().with_resources([(n, Resource.from_contents(s)) for n, s in schemas.items()])
checks = 0


def expect(name, inst, valid, why):
    global checks
    checks += 1
    errors = list(Draft202012Validator(schemas[name], registry=reg).iter_errors(inst))
    if valid and errors:
        failures.append(f"{why}: unerwartet ungueltig: {errors[0].message[:120]}")
    if not valid and not errors:
        failures.append(f"{why}: unerwartet gueltig")


def copy(x):
    return json.loads(json.dumps(x))


T = {"text": "synthetisch"}
gi = {"schema_version": "3", "session_id": "s-0000abcd", "gutachtentyp": "spf",
      "verfasserin": {"qualifikationen": ["schulpsychologin", "klinische_psychologin"]},
      "vorstellungsgrund": T, "schullaufbahn": {"schulstufe": 2, "jahr_der_schulpflicht": 2},
      "vorbefunde": [], "verhaltensbeobachtung": T,
      "anamnese": [{"quelle_id": "q1", "erhoben_mit": "die Mutter", "art": "gespraech", "uebersetzungshilfe": True, "text": "x"}],
      "testergebnisse": [{"testergebnis_id": "t1", "verfahren": "Verfahren A", "testkatalog_id": None, "einzeltestung": True,
                          "gesamt_iq": 80, "ki_untergrenze": 75, "ki_obergrenze": 86, "ki_niveau": 0.95,
                          "werte": [{"ebene": "index", "kennung": "I1", "wert": 80, "skala": "iq"}]}],
      "leistungsproben": {"deutsch": {"lesen": T, "schreiben": T}, "mathematik": T},
      "foerderung_und_umfeld": T,
      "adaptives_verhalten": {"befragte_rollen": ["die Klassenlehrerin"], "text": ""},
      "drei_quellen": {"klinischer_eindruck": "dokumentiert", "intelligenztest": "dokumentiert", "befragung_adaptives_verhalten": "fehlt"},
      "erstsprache_deutsch": False, "schulbesuch_oesterreich_monate": 14,
      "alter": {"jahre": 8, "monate": 4, "abgeleitet": True}, "empfehlung": {"text": "x", "spf_empfohlen": True}}
G = "gutachten-input.schema.json"
expect(G, gi, True, "gueltiger SPF-Input mit vollstaendigem KI")
bad = copy(gi); del bad["leistungsproben"]; expect(G, bad, False, "SPF ohne Leistungsproben")
bad = copy(gi); bad["gutachten_diagnose"] = {"text": "x"}; expect(G, bad, False, "SPF-Input mit Diagnose")
bad = copy(gi); bad["diagnose"] = {"text": "x"}; expect(G, bad, False, "altes Feld diagnose")
bad = copy(gi); bad["gutachtentyp"] = "lrs"; bad["gutachten_diagnose"] = {"text": "x"}
expect(G, bad, True, "LRS mit Diagnose und Q1")
bad["verfasserin"]["qualifikationen"] = ["schulpsychologin"]; expect(G, bad, False, "LRS-Diagnose ohne Q1")
bad = copy(gi); del bad["testergebnisse"][0]["ki_obergrenze"]; expect(G, bad, False, "Gesamt-IQ ohne vollstaendiges KI")
bad = copy(gi); bad["testergebnisse"][0]["werte"][0]["ebene"] = "gesamt"; expect(G, bad, False, "Gesamtwert doppelt in werte")
bad = copy(gi); bad["name_kind"] = "Erika"; expect(G, bad, False, "unbekanntes Klardatenfeld")
bad = copy(gi); bad["anamnese"][0]["erhoben_mit"] = "Frau Muster"; expect(G, bad, False, "Name statt Rolle")
ge = copy(gi); ge["gutachtentyp"] = "emotional_soziale_entwicklung"; expect(G, ge, True, "Typ emotional-soziale Entwicklung")

zeile = {"kennung": "I1", "wert_quelle": "/testergebnisse/0/werte/0", "kategorie": "Kategorie A"}
rg = {"regelwerk_version": "1", "testkatalog_version": "1", "gesamt": "nicht_pruefbar",
      "ergebnisse": [{"regel_id": "spf_s1", "regel_version": "1", "regel_status": "entwurf", "wirkung": "blockiert_export",
                      "ergebnis": "nicht_pruefbar", "begruendung": "x", "felder": ["/testergebnisse"]}]}
out = {"schema_version": "3", "session_id": "s-0000abcd", "gutachtentyp": "spf", "vorlage_id": "spf-wisc", "entwurf_version": 1,
       "regelergebnis": rg, "platzhalter": ["name_kind", "geschaeftszahl"],
       "abschnitte": [
           {"abschnitt_id": "vorstellungsgrund", "absaetze": [{"absatz_id": "a1", "saetze": [
               {"text": "Synthetischer Satz.", "quellen": ["/vorstellungsgrund"]},
               {"luecke": {"feld": "/adaptives_verhalten", "hinweis": "fehlt"}}]}]},
           {"abschnitt_id": "testbefunde", "tabellen": [{"testergebnis_id": "t1", "baustein_quelle": "verfahren-a", "zeilen": [zeile]}]}]}
O = "gutachten-output.schema.json"
expect(O, out, True, "gueltiger Entwurf")
bad = copy(out); bad["abschnitte"][0]["absaetze"][0]["saetze"][0]["quellen"] = []; expect(O, bad, False, "Satz ohne Quelle")
bad = copy(out); del bad["abschnitte"][1]["tabellen"][0]["zeilen"][0]["wert_quelle"]; expect(O, bad, False, "Kategorie ohne Wert")
bad = copy(out); del bad["abschnitte"][1]["tabellen"][0]["zeilen"][0]["kategorie"]; expect(O, bad, False, "Zeile ohne Kategorie und Luecke")
bad = copy(out); bad["abschnitte"].append({"abschnitt_id": "diagnose", "absaetze": []}); expect(O, bad, False, "SPF mit Diagnoseabschnitt")
bad["gutachtentyp"] = "lrs"; expect(O, bad, True, "LRS mit Diagnoseabschnitt")
bad = copy(out); bad["abschnitte"][0]["abschnitt_id"] = "befund"; expect(O, bad, False, "Abschnitt nicht in der Vorlage")
bad = copy(out); bad["platzhalter"] = ["telefon"]; expect(O, bad, False, "Platzhalter aus Vorlage-Schema")
bad = copy(out); bad["regelergebnis"]["ergebnisse"][0]["regel_id"] = "awmf_b"; expect(O, bad, False, "AWMF-Regel im Entwurf")
bad = copy(out); bad["regelergebnis"]["schweregrad_vorschlag"] = {"stufe": "leicht", "hinweis": "x"}; expect(O, bad, False, "Schweregrad im Entwurf")
bad = copy(out); del bad["regelergebnis"]["ergebnisse"][0]["wirkung"]; expect(O, bad, False, "Regelergebnis ohne Wirkung")

S = "kategorienskala.schema.json"
sk = {"skala": "iq", "von": 1, "bis": 2, "bezeichnung": "x", "quelle": "synthetisch fuer Tests", "status": "entwurf", "herkunft": "synthetisch"}
expect(S, {"schema_version": "2", "version": "1", "eintraege": [sk]}, True, "synthetische Skala")
bad = copy(sk); bad["quelle"] = ""; expect(S, {"schema_version": "2", "version": "1", "eintraege": [bad]}, False, "Skala ohne Quelle")
bad = copy(sk); del bad["herkunft"]; expect(S, {"schema_version": "2", "version": "1", "eintraege": [bad]}, False, "Skala ohne Herkunft")

K = "testkatalog.schema.json"
A = {"jahre": 6, "monate": 0}
kat = {"id": "lesetest-a", "name": "Lesetest A", "art": "leistungstest", "altersbereich": {"von": A, "bis": A}, "normart": "klasse",
       "normjahr": 2000, "einzeltestung": True, "mehrdimensional": False, "indizes": [], "beschreibungsbaustein": {"text": "t", "zitat": "z"},
       "quelle": {"manual": "synthetisch", "seite": "1"}, "status": "entwurf", "befuellt_von": "psychologin"}
expect(K, {"schema_version": "3", "version": "1", "eintraege": [kat]}, True, "Leistungstest ohne IQ-Messbereich")
bad = copy(kat); bad["art"] = "intelligenztest"; expect(K, {"schema_version": "3", "version": "1", "eintraege": [bad]}, False, "Intelligenztest ohne Messbereich")

V = "vorlage.schema.json"
vl = {"schema_version": "1", "vorlage_id": "spf-wisc", "version": "1", "gutachtentyp": "spf", "datei": "vorlage.docx",
      "abschnitte": [{"abschnitt_id": "anamnese", "ueberschrift": "Anamnese"}],
      "kopffelder": [{"platzhalter": "name_kind", "bezeichnung": "Name"}], "status": "entwurf"}
expect(V, vl, True, "gueltige Vorlage")
bad = copy(vl); bad["datei"] = "../repo/vorlage.docx"; expect(V, bad, False, "Vorlagenpfad ausserhalb")

R = "regelwerk.schema.json"
rw = {"schema_version": "1", "version": "1", "regeln": [{"regel_id": "spf_s1", "version": "1", "titel": "t", "beschreibung": "b",
      "quelle": {"dokument": "BGBl. II Nr. 280/2024, Anlage 1", "fassung": "2024"}, "status": "entwurf", "parameter": {}}]}
expect(R, rw, False, "Regel ohne Gutachtentyp")
rw["regeln"][0]["gutachtentyp"] = ["spf"]; expect(R, rw, True, "Regel mit Gutachtentyp")

FUNDE = {"direkte_identifikatoren": 0, "datumsangaben": 0, "orte_einrichtungen": 0, "seltene_merkmale": 0,
         "versteckte_inhalte": 0, "bilder": 0, "unsicher": 0}
ses = {"schema_version": "1", "session_id": "s-0000abcd", "bezeichnung": "Fall 1", "modus": "gutachten", "gutachtentyp": "spf",
       "status": "import", "versionen": {"regelwerk": "1", "testkatalog": "1"},
       "dokumente": [{"dok_id": "d-0000abcd", "format": "pdf_scan", "quelle_rolle": "Bericht",
                      "freigabe": {"status": "freigegeben", "funde_je_kategorie": FUNDE}}]}
SE = "session.schema.json"
expect(SE, ses, False, "Freigabe ohne Bestaetigung")
ses["dokumente"][0]["freigabe"]["geprueft_bestaetigt"] = True; expect(SE, ses, True, "Freigabe mit Bestaetigung")
bad = copy(ses); bad["dokumente"][0]["freigabe"]["funde_je_kategorie"]["unsicher"] = 2; expect(SE, bad, False, "Freigabe trotz unsicherer Funde")
bad = copy(ses); bad["dokumente"][0]["freigabe"]["status"] = "offen"; bad["dokumente"][0]["text_anonymisiert"] = "x"
expect(SE, bad, False, "anonymisierter Text ohne Freigabe")
bad = copy(ses); bad["dokumente"][0]["freigabe"]["funde_je_kategorie"] = {}; expect(SE, bad, False, "Freigabe ohne Fundzaehlung")

rollen = {"fallerzaehlerin": "psychologin", "moderation": "ki", "berater": [{"berater_id": "b1", "perspektive": "Mehrsprachigkeit und DaZ"}]}
bf = {"befund_id": "bf-0000abcd", "stelle": {"abschnitt_id": "empfehlung"}, "problem": "p", "schwere": "mittel",
      "begruendung": "b", "pruefer": "elefant", "entscheidung": {"status": "offen"}}
IV = "protokoll-intervision.schema.json"
iv_ok = {"schema_version": "1", "session_id": "s-0000abcd", "phase": "beendet", "rollen": rollen,
         "schluesselfrage": {"endgueltig": "x", "bestaetigt": True}, "methode": "resonanzrunde",
         "beratung": [{"runde": 1, "berater_id": "b1", "beitrag": "x"}], "pruefbefunde": [bf], "abschluss": {"mitnahme": "x"}}
expect(IV, iv_ok, True, "vollstaendiges beendetes Protokoll")
bad = copy(iv_ok); del bad["abschluss"]; expect(IV, bad, False, "beendet ohne Abschluss")
bad = copy(iv_ok); bad["phase"] = "abgebrochen"; bad["abbruch"] = {"grund": "kindeswohlgefaehrdung", "hinweis": "x"}
expect(IV, bad, False, "Kindeswohl ist kein Abbruchgrund")
bad = copy(iv_ok); bad["phase"] = "beratung"; bad["hinweise"] = [{"art": "kindeswohl", "text": "Gefaehrdungsmeldung an die MA 11 koennte noetig sein."}]
expect(IV, bad, True, "Kindeswohl als Hinweis")

SV = "protokoll-supervision.schema.json"
sv = {"schema_version": "1", "session_id": "s-0000abcd", "status": "beendet", "ki_kennzeichnung": True, "haltung_version": "1",
      "anliegen": "x", "ebenen": [{"ebene": "rolle_und_system"}], "goldfisch_befunde": [], "abschluss": {"mitnahme": "x"}}
expect(SV, sv, True, "beendete Supervision")
bad = copy(sv); bad["ki_kennzeichnung"] = False; expect(SV, bad, False, "Supervision ohne KI-Kennzeichnung")

ST = "stilprofil.schema.json"
sp = {"schema_version": "1", "version": "1", "status": "entwurf", "anzahl_probegutachten": 1,
      "merkmale": [{"merkmal_id": "m1", "kategorie": "satzbau", "beschreibung": "x", "belegzitate": [{"text": "x", "probe_id": "pg-0000abcd"}]}],
      "formulierungsbeispiele": []}
expect(ST, sp, True, "Stilprofil Entwurf")

L = "lernsignal.schema.json"
lg = {"schema_version": "1", "signal_id": "ls-0000abcd", "herkunft": "gutachten", "art": "befund_verworfen", "bereich": "sprache", "konfiguration_version": "1"}
expect(L, lg, True, "Lernsignal Sprache")
bad = copy(lg); bad["bereich"] = "bewertungslogik"; expect(L, bad, False, "Bewertungslogik kein Bereich")
bad = copy(lg); bad["herkunft"] = "supervision"; expect(L, bad, False, "Supervision liefert kein Lernsignal")

DV = "diagnosevorschlag.schema.json"
dv = {"schema_version": "1", "session_id": "s-0000abcd", "quelle": "engine", "kriterien": "nicht_pruefbar",
      "begruendung": [{"text": "x", "quellen": ["/testergebnisse/0"]}], "hinweis": "Vorschlag, keine Diagnose."}
expect(DV, dv, False, "Engine-Vorschlag ohne Regelergebnis-Version")
dv["regelergebnis_version"] = "1"; expect(DV, dv, True, "Engine-Vorschlag")
bad = copy(dv); bad["quelle"] = "claude"; bad["begruendung"][0]["quellen"] = []; expect(DV, bad, False, "Claude-Vorschlag ohne Quelle")

FP = "fallpaket.schema.json"
vl_c = copy(vl); del vl_c["datei"]
kopf = {"schema_version": "2", "paket_id": "p-0000abcd", "session_id": "s-0000abcd", "anonymisierung_geprueft": True}
gp = dict(kopf, art="gutachten", erwartete_rueckgabe="gutachten-output",
          inhalt={"gutachten_input": gi, "regelergebnis": rg, "vorlage": vl_c,
                  "kategorien": [{"wert_quelle": "/testergebnisse/0/werte/0", "kategorie": "Kategorie A"}],
                  "bausteine": [{"testkatalog_id": "verfahren-a", "text": "t", "zitat": "z"}]})
expect(FP, gp, True, "Gutachten-Paket")
bad = copy(gp); bad["inhalt"]["vorlage"] = vl; expect(FP, bad, False, "Vorlagen-Dateiname im Paket")
bad = copy(gp); bad["inhalt"]["interne_diagnose"] = {"text": "x"}; expect(FP, bad, False, "interne Diagnose im Paket")
bad = copy(gp); bad["inhalt"]["regelergebnis"]["ergebnisse"][0]["regel_id"] = "awmf_b"; expect(FP, bad, False, "AWMF-Regel im Paket")
bad = copy(gp); bad["anonymisierung_geprueft"] = False; expect(FP, bad, False, "Paket ohne erneute Erkennung")
bad = copy(gp); bad["erwartete_rueckgabe"] = "befunde"; expect(FP, bad, False, "Art und Rueckgabe entkoppelt")
gf = dict(kopf, art="pruefung_goldfisch", erwartete_rueckgabe="befunde", inhalt={"fragestellung": "x", "ergebnis_text": "y", "kriterien": "z"})
expect(FP, gf, True, "Goldfisch-Paket")
bad = copy(gf); bad["inhalt"]["gutachten_input"] = gi; expect(FP, bad, False, "Goldfisch ohne Eingaben")
el = dict(kopf, art="pruefung_elefant", erwartete_rueckgabe="befunde", inhalt={"gutachten_input": gi, "entwurf": out, "regelergebnis": rg})
expect(FP, el, True, "Elefant-Paket")
dp = dict(kopf, art="diagnosevorschlag", erwartete_rueckgabe="diagnosevorschlag", inhalt={"gutachten_input": gi})
expect(FP, dp, True, "Diagnosevorschlag-Paket")
bad = copy(dp); bad["inhalt"]["entwurf"] = out; expect(FP, bad, False, "Diagnosevorschlag mit Entwurf")
hp = dict(kopf, art="hypothese", erwartete_rueckgabe="befunde", inhalt={"vignette": "x", "schlussfolgerung": "y"})
expect(FP, hp, True, "Hypothese-Paket")
sl = dict(kopf, art="stil_lernen", erwartete_rueckgabe="stilprofil", inhalt={"probetexte": [{"probe_id": "pg-0000abcd", "text": "x"}]})
expect(FP, sl, True, "Stil-lernen-Paket")
bad = copy(sl); bad["inhalt"]["dateiname"] = "x.docx"; expect(FP, bad, False, "Stil-lernen mit Zusatzfeld")
expect(FP, dict(kopf, art="intervision", erwartete_rueckgabe="befunde", inhalt={}), False, "Intervision hat keine Paketart")

RK = "rueckgabe.schema.json"
expect(RK, {"schema_version": "2", "paket_id": "p-0000abcd", "typ": "befunde", "daten": [bf]}, True, "Rueckgabe Befunde")
bad = copy(bf); bad["entscheidung"]["status"] = "angenommen"
expect(RK, {"schema_version": "2", "paket_id": "p-0000abcd", "typ": "befunde", "daten": [bad]}, False, "Rueckgabe nimmt Entscheidung vorweg")
bad = copy(bf); bad["schwere"] = "kritisch"
expect(RK, {"schema_version": "2", "paket_id": "p-0000abcd", "typ": "befunde", "daten": [bad]}, False, "Schwere nur hoch, mittel, gering")
sp_frei = copy(sp); sp_frei["status"] = "freigegeben"
expect(RK, {"schema_version": "2", "paket_id": "p-0000abcd", "typ": "stilprofil", "daten": sp_frei}, False, "Rueckgabe gibt Stilprofil frei")
expect(RK, {"schema_version": "2", "paket_id": "p-0000abcd", "typ": "gutachten-output", "daten": out}, True, "Rueckgabe Entwurf")
dv_c = copy(dv); dv_c["quelle"] = "claude"
expect(RK, {"schema_version": "2", "paket_id": "p-0000abcd", "typ": "diagnosevorschlag", "daten": dv_c}, True, "Rueckgabe Claude-Vorschlag")
expect(RK, {"schema_version": "2", "paket_id": "p-0000abcd", "typ": "diagnosevorschlag", "daten": dv}, False, "Rueckgabe als Engine-Vorschlag")
expect(RK, {"schema_version": "2", "paket_id": "p-0000abcd", "typ": "protokoll-supervision", "daten": sv}, True, "Rueckgabe Supervision")

FS = "fallspeicher.schema.json"
fs = {"schema_version": "1", "session": ses, "gutachten_input": gi,
      "interne_diagnose": {"text": "x", "erfasst_vor_vorschlaegen": True}, "diagnosevorschlaege": [dv],
      "vergleich": {"engine": "gleich", "claude": "abweichend"}}
expect(FS, fs, True, "Fallspeicher mit Vergleich")
bad = copy(fs); del bad["interne_diagnose"]; expect(FS, bad, False, "Vergleich ohne interne Diagnose")
bad = copy(fs); bad["interne_diagnose"]["erfasst_vor_vorschlaegen"] = False; expect(FS, bad, False, "kein blinder Vergleich")

IC = "icd10-referenz.schema.json"
expect(IC, {"schema_version": "1", "version": "test", "quelle": "synthetisch", "herkunft": "synthetisch", "codes": [{"code": "X99.9", "titel": "synthetisch"}]}, True, "synthetische ICD-Liste")
expect(IC, {"schema_version": "1", "version": "test", "quelle": "synthetisch", "herkunft": "synthetisch", "codes": [{"code": "x99", "titel": "y"}]}, False, "ungueltiger Code")

if failures:
    print("\n".join(failures))
    print(f"FEHLER: {len(failures)} von {checks} Pruefungen")
    sys.exit(1)
print(f"{len(schemas)} Schemas gueltig, {checks} Pruefungen bestanden")
