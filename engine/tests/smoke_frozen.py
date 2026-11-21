"""Smoke test of the delivered engine (not part of pytest): MCP cold start, and a ui run with import, OCR,
recognition and release. Usage: python tests/smoke_frozen.py <start command>, for the bundle of
scripts/build_engine.py: python tests/smoke_frozen.py <bundle>/python/python.exe -m schlomo_engine"""
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import synth_files as sf  # noqa: E402

cmd = sys.argv[1:]
tmp = Path(tempfile.mkdtemp())
env = dict(os.environ, SCHLOMO_DATA_DIR=str(tmp / "daten"))
work = tmp / "arbeitsordner"
work.mkdir()


def mcp_start() -> float:
    t0 = time.perf_counter()
    p = subprocess.Popen([*cmd, "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         env=env, cwd=work)
    p.stdin.write((json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "s", "version": "0"}}}) + "\n").encode())
    p.stdin.flush()
    while json.loads(p.stdout.readline()).get("id") != 1:
        pass
    dt = time.perf_counter() - t0
    p.kill()
    return dt


times = [mcp_start() for _ in range(5)]
print(f"mcp start_bis_initialize_s: erster={times[0]:.2f} median={statistics.median(times):.2f} alle={[round(t, 2) for t in times]}")

sf.make_docx(tmp / "a.docx")
png = sf.make_images(tmp)["png"]
ui = subprocess.Popen([*cmd, "ui"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=work)


def call(fn, **args):
    ui.stdin.write((json.dumps({"id": f"r-{fn}", "fn": fn, "args": args}) + "\n").encode())
    ui.stdin.flush()
    while True:
        msg = json.loads(ui.stdout.readline())
        if "ok" in msg:
            return msg


t0 = time.perf_counter()
print("status", call("status")["ok"], f"{time.perf_counter() - t0:.2f}s")
answer = call("sitzung_anlegen", bezeichnung="Fall 1", modus="supervision")
assert answer["ok"], answer
sid = answer["result"]["session"]["session_id"]
print("namen", call("bekannte_namen_setzen", session_id=sid, namen=[{"text": "SYN-HAUPTTEXT", "rolle": "das Kind"}])["ok"])
dok = call("dokument_importieren", session_id=sid, pfad=str(tmp / "a.docx"), quelle_rolle="Bericht")["result"]["dok_id"]
t0 = time.perf_counter()
funde = call("erkennung_ausfuehren", session_id=sid, dok_id=dok)["result"]
print("erkennung (inkl. Laden des Modells)", f"{time.perf_counter() - t0:.2f}s", "funde", len(funde["funde"]))
img = call("dokument_importieren", session_id=sid, pfad=str(png), quelle_rolle="Foto")["result"]["dok_id"]
ocr = call("ocr_ausfuehren", session_id=sid, dok_id=img)["result"]
print("ocr", ocr)
assert ocr["seiten_erkannt"] == 1
for f in funde["funde"]:
    if f["status"] == "offen":
        call("schwaerzung_entscheiden", session_id=sid, dok_id=dok, fund_id=f["fund_id"], entscheidung="uebernehmen")
freigabe = call("anonymisierung_freigeben", session_id=sid, dok_id=dok, geprueft_bestaetigt=True)["result"]["freigabe"]
print("freigabe", freigabe["status"])
assert freigabe["status"] == "freigegeben" and funde["funde"]
call("beenden")
assert ui.wait(timeout=30) == 0

# hook start type: a file tool is blocked with exit code 2, an engine tool passes
blocked = subprocess.run([*cmd, "hook"], input=json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x"}}).encode(),
                         capture_output=True, env=env, cwd=work, timeout=60)
allowed = subprocess.run([*cmd, "hook"], input=json.dumps({"tool_name": "mcp__engine__hole_entwurf"}).encode(),
                         capture_output=True, env=env, cwd=work, timeout=60)
print("hook", blocked.returncode, allowed.returncode)
assert blocked.returncode == 2 and allowed.returncode == 0
print("RAUCHTEST BESTANDEN")
