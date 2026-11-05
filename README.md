# CollectIQ

A receivables operations assistant. It records invoice and payment evidence, keeps balances derived
from human-confirmed allocations, and pauses follow-ups when anything is uncertain. It does not replace
an accounting system, and it never marks an invoice paid on its own.

Status and limitations: [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).

## Prerequisites

Podman, [uv](https://docs.astral.sh/uv/), Node 24, make.

## Run it locally

```bash
make db-up     # creates .env with random local secrets, starts Postgres on 127.0.0.1:54329
make migrate
make seed      # optional, synthetic sample data, labelled as sample in the UI
make dev       # API :8000, worker, web :5173
```
