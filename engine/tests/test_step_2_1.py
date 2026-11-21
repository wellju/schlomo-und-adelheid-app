"""Step 2.1: working folder template and its blocks (hook start type, settings, .mcp.json). Synthetic only."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from schlomo_engine import hook

TEMPLATE = Path(__file__).resolve().parents[2] / "arbeitsordner"

# Every attempt to reach a file, a shell or the web, with synthetic paths for the cases of the step table.
BLOCKED = [
    ("Read", {"file_path": "D:/Profile/syn/Desktop/ausserhalb.txt"}),
    ("Read", {"file_path": "C:/Claude privat/Schlomo und Adelheid/Context/SYN-KONTEXT.docx"}),
    ("Read", {"file_path": "D:/Profile/syn/Documents/Schlomo-Rohdaten/SYN-ROH.pdf"}),
    ("Read", {"file_path": "./bericht.docx"}), ("Read", {"file_path": "./scan.pdf"}), ("Read", {"file_path": "./foto.png"}),
    ("Grep", {"pattern": "SYN", "path": "Context"}), ("Glob", {"pattern": "**/*.docx"}),
    ("Edit", {"file_path": "x.md"}), ("Write", {"file_path": "x.md", "content": "x"}), ("NotebookEdit", {"notebook_path": "a.ipynb"}),
    ("Bash", {"command": "type Context\\SYN.txt"}), ("PowerShell", {"command": "Get-Content Context/SYN.txt"}),
    ("WebFetch", {"url": "https://example.org"}), ("WebSearch", {"query": "x"}),
    ("mcp__claude-in-chrome__navigate", {"url": "file:///C:/Context/SYN.txt"}),
    ("mcp__computer-use__screenshot", {}), ("mcp__ccd_session__start_session", {}), ("UnbekanntesWerkzeug", {}),
    ("SendMessage", {"to": "andere-session", "message": "x"}),
]
ALLOWED = ["mcp__engine__hole_gutachten_input", "mcp__engine__hole_goldfisch_paket", "Agent", "Skill", "ToolSearch", "SubagentHandback",
           "TodoWrite", "mcp__ccd_turn__update_plan"]


def _run(payload: bytes, env) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "schlomo_engine", "hook"], input=payload, capture_output=True,
                          env=env["env"], cwd=env["work"], timeout=60)


@pytest.mark.parametrize("tool,tool_input", BLOCKED)
def test_blocked(tool, tool_input):
    assert hook.decide({"tool_name": tool, "tool_input": tool_input}) is not None


@pytest.mark.parametrize("tool", ALLOWED)
def test_allowed(tool):
    assert hook.decide({"tool_name": tool, "tool_input": {}}) is None


@pytest.mark.parametrize("event", [None, [], {}, {"tool_name": ""}, {"tool_name": 3}])
def test_malformed_input_is_blocked(event):
    assert hook.decide(event) is not None


def test_hook_over_the_real_process(env):
    """Exit code 2 blocks (docs: hooks, PreToolUse); the reason names the tool, never the path."""
    out = _run(json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Read",
                           "tool_input": {"file_path": "C:/Context/SYN-PFAD-1234.docx"}}).encode(), env)
    assert out.returncode == 2 and "Read" in out.stderr.decode("utf-8") and "SYN-PFAD" not in out.stderr.decode("utf-8")
    ok = _run(json.dumps({"tool_name": "mcp__engine__hole_entwurf", "tool_input": {"session_id": "s-00000000"}}).encode(),
              env)
    assert ok.returncode == 0 and ok.stdout == b"" and ok.stderr == b""
    assert _run(b"kein json", env).returncode == 2


def test_hook_start_loads_no_heavy_module(env):
    probe = ("import sys, runpy; sys.argv = ['engine', 'hook']; import schlomo_engine.hook; "
             "print(sorted(n for n in sys.modules if n.split('.')[0] in ('spacy', 'mcp', 'jsonschema', 'lxml', "
             "'pikepdf', 'PIL', 'pypdfium2', 'openpyxl') or n in ('schlomo_engine.importer', "
             "'schlomo_engine.recognition', 'schlomo_engine.store')))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True, env=env["env"], timeout=60)
    assert out.stdout.decode().strip() == "[]"


def test_settings_template():
    settings = json.loads((TEMPLATE / ".claude" / "settings.json").read_text(encoding="utf-8"))
    deny = set(settings["permissions"]["deny"])
    assert {"Bash", "PowerShell", "Read", "Edit", "Write", "NotebookEdit", "Grep", "Glob", "WebFetch", "WebSearch"} <= deny
    assert "Read(//**/Context/**)" in deny and "Read(~/Documents/Schlomo-Rohdaten/**)" in deny
    # Desktop MCP servers with file, screen or web access are removed by name too (Code-Tab test, 21.11.2026)
    assert {"mcp__terminal", "mcp__Claude_Browser", "mcp__computer-use", "mcp__claude-in-chrome"} <= deny
    assert not any(d.startswith("mcp__engine") for d in deny)
    assert {f"Read(//**/*.{e})" for e in ("docx", "doc", "dotx", "xlsx", "xls", "pdf", "jpg", "jpeg", "png", "heic")} <= deny
    assert settings["permissions"]["blockReadsOutsideWorkingDirectories"] is True
    assert settings["permissions"]["disableBypassPermissionsMode"] == "disable"
    assert "allow" not in settings["permissions"]  # nothing is opened up
    (group,) = settings["hooks"]["PreToolUse"]
    # onFailure block: a hook that cannot start blocks the call instead of letting it through (hooks doc, E03)
    assert group["matcher"] == "*" and group["hooks"] == [{"type": "command", "command": "{{ENGINE_EXE}}", "args": ["hook"],
                                                           "onFailure": "block"}]
    assert settings["enabledMcpjsonServers"] == ["engine"]
    # desktopSessionCleanupPeriodDays has scope "User or managed" (settings reference): never in project settings
    assert "desktopSessionCleanupPeriodDays" not in settings


def test_mcp_and_user_templates():
    mcp = json.loads((TEMPLATE / ".mcp.json").read_text(encoding="utf-8"))
    assert mcp == {"mcpServers": {"engine": {"command": "{{ENGINE_EXE}}", "args": ["mcp"]}}}
    user = json.loads((TEMPLATE / "benutzer-einstellungen.json").read_text(encoding="utf-8"))
    assert set(user) == {"desktopSessionCleanupPeriodDays"} and isinstance(user["desktopSessionCleanupPeriodDays"], int)


def test_claude_md_holds_no_case_data_or_instructions():
    """Subagents read CLAUDE.md (spike point 1): no case data, no rule or wording that steers a reviewer."""
    text = (TEMPLATE / "CLAUDE.md").read_text(encoding="utf-8")
    for word in ("Goldfisch", "Elefant", "Diagnose", "SPF", "ICD", "Kategorie", "Gefälligkeit", "empfohlen"):
        assert word not in text, word
