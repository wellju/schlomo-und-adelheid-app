"""Test helpers. Synthetic data only."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Installer model (user decision, step 1.3); the model comparison runs separately (tests/evaluate.py).
os.environ.setdefault("SCHLOMO_SPACY_MODEL", "de_core_news_md")

SRC = Path(__file__).resolve().parents[1] / "src"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Data folder and working folder as siblings in tmp, never inside the repo."""
    data, work = tmp_path / "daten", tmp_path / "arbeitsordner"
    work.mkdir()
    monkeypatch.setenv("SCHLOMO_DATA_DIR", str(data))
    monkeypatch.chdir(work)
    e = dict(os.environ, PYTHONPATH=str(SRC), SCHLOMO_DATA_DIR=str(data), PYTHONIOENCODING="utf-8")
    return {"data": data, "work": work, "env": e}


def run_ui(env, requests: list) -> tuple[list[dict], str]:
    """Start `engine ui` as a real subprocess, send raw lines, return answers and stderr."""
    lines = "".join((r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)) + "\n" for r in requests)
    proc = subprocess.run([sys.executable, "-m", "schlomo_engine", "ui"], input=lines.encode("utf-8"),
                          capture_output=True, env=env["env"], cwd=env["work"], timeout=60)
    answers = [json.loads(line) for line in proc.stdout.decode("utf-8").splitlines() if line.strip()]
    return answers, proc.stderr.decode("utf-8")


def read_json_line(proc, timeout: float = 60) -> dict:
    """One JSON line from a subprocess, with a time limit so a hanging server never hangs the test run (EGM E41)."""
    import threading
    box: list = []
    reader = threading.Thread(target=lambda: box.append(proc.stdout.readline()), daemon=True)
    reader.start()
    reader.join(timeout)
    if not box or not box[0]:
        proc.kill()
        raise TimeoutError("no answer from engine subprocess")
    return json.loads(box[0])


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """SCHLOMO_ABNAHME=1 turns every skip into a failure, so an acceptance run cannot pass with missing tools
    (EGM E24)."""
    outcome = yield
    report = outcome.get_result()
    if os.environ.get("SCHLOMO_ABNAHME") == "1" and report.skipped:
        report.outcome = "failed"
        report.longrepr = "Abnahmelauf: Test übersprungen, Werkzeug fehlt"
