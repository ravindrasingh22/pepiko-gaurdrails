# PikuAI Gaurdrails

Standalone production scaffold for the PikuAI guardrail pipeline.

This repo keeps:

- `notebooks/` for experiments, dataset work, training, and release validation
- `app/` for production runtime code
- `configs/` for admin-owned policy and routing controls
- `training/` for repeatable scripts
- `tests/` for safety regression coverage

The runtime exposes one production guardrail entrypoint:

- `POST /api/v1/guardrails/run`

It also includes three scaffolded backend test endpoints:

- `POST /api/v1/guardrails/test/classification`
- `POST /api/v1/guardrails/test/llm-call`
- `POST /api/v1/guardrails/test/validator`

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 4001
```

## Docker

```bash
docker compose up --build
```

API:

```text
http://localhost:4001/api/v1/guardrails/run
```

Backend test endpoints use the same base URL under `/api/v1/guardrails/test/...`.

See [docs/architecture.md](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/architecture.md) for the target production design.
