"""Entry point: `engine ui` (app sidecar, JSON lines) or `engine mcp` (MCP server)."""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="engine")
    parser.add_argument("startart", choices=["ui", "mcp"])
    args = parser.parse_args(argv)
    if args.startart == "ui":
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
        from .external import cleanup_stale
        from .protocol import serve
        cleanup_stale()
    else:
        from .mcp_server import serve  # imports nothing from import or recognition
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
