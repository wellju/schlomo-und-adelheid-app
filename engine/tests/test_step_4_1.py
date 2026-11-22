"""Step 4.1: app settings over the ui channel (Screen 13). Synthetic."""
from conftest import run_ui


def test_settings_default_save_reload(env):
    neu = {"schema_version": "1", "verbindung": "browser", "qualifikationen": ["schulpsychologin", "klinische_psychologin"],
           "darstellung": "dunkel"}
    answers, _ = run_ui(env, [{"id": "1", "fn": "einstellungen_laden"},
                              {"id": "2", "fn": "einstellungen_speichern", "args": {"einstellungen": neu}},
                              {"id": "3", "fn": "einstellungen_laden"}])
    assert answers[0]["result"]["einstellungen"]["verbindung"] == "desktop"
    assert answers[0]["result"]["einstellungen"]["qualifikationen"] == []
    assert answers[0]["result"]["vorhanden"] is False and answers[2]["result"]["vorhanden"] is True
    assert answers[1]["ok"] and answers[2]["result"]["einstellungen"] == neu
    assert (env["data"] / "einstellungen.json").exists()


def test_settings_reject_invalid(env):
    answers, _ = run_ui(env, [{"id": "1", "fn": "einstellungen_speichern",
                               "args": {"einstellungen": {"schema_version": "1", "verbindung": "telefon",
                                                          "qualifikationen": [], "darstellung": "hell"}}},
                              {"id": "2", "fn": "einstellungen_speichern", "args": {}}])
    assert [a["fehler"]["code"] for a in answers] == ["E_SCHEMA", "E_SCHEMA"]
    assert not (env["data"] / "einstellungen.json").exists()


def test_broken_settings_file_does_not_stop_the_app(env):
    """EGM C17: a broken file gives the defaults and says so; the app still starts."""
    env["data"].mkdir(parents=True, exist_ok=True)
    (env["data"] / "einstellungen.json").write_text("{kaputt", encoding="utf-8")
    answers, _ = run_ui(env, [{"id": "1", "fn": "einstellungen_laden"}])
    assert answers[0]["ok"] and answers[0]["result"]["beschaedigt"] is True and answers[0]["result"]["vorhanden"] is False
