"""Start type hook: PreToolUse hook for the working folder (Task 2.1). Second layer behind the deny rules in
arbeitsordner/.claude/settings.json: only the engine's MCP tools and a few orchestration tools run, every other tool
call is blocked with exit code 2. Claude never needs a file, a shell or the web in the working folder; all case data
comes from the engine. Reads only stdin, imports nothing from import or recognition, writes no log (the reason on
stderr goes to Claude and names only the tool)."""
import json
import sys

# Orchestration without access to files, shell or network. ToolSearch loads deferred MCP tool schemas;
# SubagentHandback is how a subagent returns its report in Claude Desktop (seen in the Code-Tab test, 21.11.2026).
# SendMessage stays blocked: it can carry text to other sessions.
ALLOWED = frozenset({"Agent", "Task", "Skill", "ToolSearch", "TodoWrite", "TaskCreate", "TaskUpdate", "TaskList",
                     "TaskGet", "AskUserQuestion", "EnterPlanMode", "ExitPlanMode", "SubagentHandback"})
ALLOWED_PREFIXES = ("mcp__engine__", "mcp__ccd_turn__")  # engine tools; the desktop app's task list


def decide(event: dict) -> str | None:
    """None if the call may run, else the reason. Unknown and malformed input is blocked."""
    tool = event.get("tool_name") if isinstance(event, dict) else None
    if not isinstance(tool, str) or not tool:
        return "Werkzeugaufruf ohne Namen blockiert."
    if tool in ALLOWED or tool.startswith(ALLOWED_PREFIXES):
        return None
    return (f"Im Arbeitsordner gesperrt: {tool}. Falldaten kommen nur über die Engine-Werkzeuge; Dateien, Shell und "
            "Web sind hier nicht erlaubt.")


def main() -> int:
    try:
        event = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        event = None
    reason = decide(event)
    if reason is None:
        return 0
    sys.stderr.write(reason + "\n")
    return 2  # PreToolUse: exit code 2 blocks the call, stderr is the reason
