"""Stdlib load runner (k6 is not required). Same read mix as read_models.js; prints p50/p95/p99, rps, errors.

Run: BASE=http://127.0.0.1:8000 WS=.. EMAIL=.. PASSWORD=.. [VUS=5 SECONDS=30] uv run python perf/measure.py
"""

import http.cookiejar
import json
import os
import statistics
import threading
import time
import urllib.request

BASE, WS = os.environ["BASE"], os.environ["WS"]
VUS, SECONDS = int(os.environ.get("VUS", 5)), int(os.environ.get("SECONDS", 30))
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
login = urllib.request.Request(
    f"{BASE}/api/v1/auth/login",
    json.dumps({"email": os.environ["EMAIL"], "password": os.environ["PASSWORD"]}).encode(),
    {"Content-Type": "application/json"},
)
opener.open(login).read()
root = f"{BASE}/api/v1/workspaces/{WS}"
first = json.load(opener.open(f"{root}/invoices?limit=1"))
invoice = (first.get("items") or first.get("data"))[0]["id"]
MIX = {
    "list": f"{root}/invoices?limit=50&sort=due_date",
    "list-overdue": f"{root}/invoices?tile=overdue&limit=50",
    "queue": f"{root}/queue?limit=50",
    "dashboard": f"{root}/dashboard",
    "detail": f"{root}/invoices/{invoice}",
}
samples: dict[str, list[float]] = {k: [] for k in MIX}
errors = 0
lock = threading.Lock()
deadline = time.monotonic() + SECONDS


def worker() -> None:
    global errors
    cookie = "; ".join(f"{c.name}={c.value}" for c in jar)
    while time.monotonic() < deadline:
        for name, url in MIX.items():
            t = time.perf_counter()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"Cookie": cookie})) as r:
                    r.read()
                    ok = r.status == 200
            except Exception:  # noqa: BLE001
                ok = False
            ms = (time.perf_counter() - t) * 1000
            with lock:
                samples[name].append(ms)
                errors += not ok


start = time.monotonic()
threads = [threading.Thread(target=worker) for _ in range(VUS)]
[t.start() for t in threads]
[t.join() for t in threads]
elapsed = time.monotonic() - start
total = sum(len(v) for v in samples.values())
print(f"vus={VUS} seconds={elapsed:.0f} requests={total} rps={total / elapsed:.1f} errors={errors}")
for name, v in samples.items():
    q = statistics.quantiles(v, n=100)
    print(f"{name:13s} n={len(v):5d} p50={q[49]:7.1f}ms p95={q[94]:7.1f}ms p99={q[98]:7.1f}ms")
