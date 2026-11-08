# Measured read performance (local, single machine)

Run on 2026-11-08 with `backend/perf/measure.py` (stdlib threaded client) against gunicorn
(4 sync workers, `collectiq.settings.local`, so no TLS redirect) and PostgreSQL 16 in the
`collectiq-db` container, **all on one 16-core / 15 GB workstation that also ran the client**.
Workspace from `perf/setup_read_models.py` (about 5,000 invoices). Mix: invoice list, overdue list,
follow-up queue, dashboard, invoice detail, evenly weighted, read-only, one logged-in user per run.

| Virtual users | Duration | Requests | Throughput | Errors | List p50/p95/p99 (ms) | Queue p50/p95/p99 | Dashboard p50/p95/p99 | Detail p50/p95/p99 |
|---|---|---|---|---|---|---|---|---|
| 1 | 30 s | 295 | 9.8 req/s | 0 | 123 / 162 / 883 | 106 / 150 / 195 | 122 / 163 / 193 | 8 / 13 / 69 |
| 5 | 30 s | 1,205 | 39.5 req/s | 0 | 143 / 214 / 265 | 142 / 211 / 241 | 149 / 218 / 246 | 24 / 85 / 100 |
| 20 | 31 s | 1,210 | 39.4 req/s | 0 | 442 / 617 / 654 | 607 / 657 / 686 | 615 / 691 / 711 | 339 / 522 / 541 |

Reading it honestly:
- All runs are inside the NFR-01 targets (dashboard and queue p95 ≤ 2 s, list and detail p95 ≤ 1 s) on this setup.
- Throughput saturates near 40 req/s with 4 workers; at 20 users latency is queueing, not slower queries.
- Runs are 30 s each, one machine, client and server competing for CPU, no network latency, no TLS,
  no other tenants, warm caches. They show the read paths are not pathological. They are **not** a
  production capacity or uptime guarantee, and write paths and the nightly scheduler are not covered here.
- Reproduce: seed with `perf/setup_read_models.py`, start the server, then
  `BASE=… WS=… EMAIL=… PASSWORD=… VUS=5 SECONDS=30 python backend/perf/measure.py`.
  The k6 script `backend/perf/read_models.js` expresses the same thresholds; k6 is not installed here.
