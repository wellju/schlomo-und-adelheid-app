"""PyInstaller entry point: one program, start types ui and mcp (ADR 0001)."""
import sys

from schlomo_engine.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
