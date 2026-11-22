"""Step 4.6: first start sets up the working folder with this engine, konfiguration/ and wissensbasis/."""
import json

import pytest

from schlomo_engine import config, ui_functions as uf
from schlomo_engine.errors import EngineError


def test_setup_working_folder(env, tmp_path, monkeypatch):
    monkeypatch.delenv("SCHLOMO_KONFIGURATION", raising=False)
    monkeypatch.delenv("SCHLOMO_VORLAGEN", raising=False)
    assert uf.FUNCTIONS["einrichten_status"]({})["eingerichtet"] is False
    assert config.config_dir() is None  # nothing configured before the setup
    ziel = tmp_path / "Schlomo Arbeitsordner"
    out = uf.FUNCTIONS["einrichten"]({"arbeitsordner": str(ziel)})
    assert out["eingerichtet"] and out["arbeitsordner"] == str(ziel.resolve())
    mcp = json.loads((ziel / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["engine"]
    assert mcp["args"][-1] == "mcp" and "{{" not in json.dumps(mcp)
    hook = json.loads((ziel / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]
    assert hook["args"][-1] == "hook" and hook["onFailure"] == "block" and "{{" not in hook["command"]
    assert (ziel / ".claude" / "skills" / "gutachten" / "SKILL.md").is_file()
    assert config.config_dir() == env["data"].resolve().parent / "konfiguration"
    assert (env["data"].resolve().parent / "wissensbasis" / "vorlagen").is_dir()
    with pytest.raises(EngineError) as e:  # never over a folder with content
        uf.FUNCTIONS["einrichten"]({"arbeitsordner": str(ziel)})
    assert e.value.code == "E_BLOCKIERT"
    with pytest.raises(EngineError) as e:  # never around the case store
        uf.FUNCTIONS["einrichten"]({"arbeitsordner": str(env["data"].parent)})
    assert e.value.reason == "datenordner"


def test_engine_started_from_the_new_folder_answers(env, tmp_path):
    """The command written into .mcp.json really starts this engine (start type hook answers on empty input)."""
    import subprocess
    ziel = tmp_path / "ao"
    uf.FUNCTIONS["einrichten"]({"arbeitsordner": str(ziel)})
    hook = json.loads((ziel / ".claude" / "settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]
    probe = json.dumps({"tool_name": "mcp__engine__liste_sitzungen", "tool_input": {}})
    r = subprocess.run([hook["command"], *hook["args"]], input=probe.encode(), capture_output=True, cwd=ziel, timeout=60)
    assert r.returncode == 0, r.stderr
