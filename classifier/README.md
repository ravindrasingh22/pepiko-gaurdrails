# PikuAI Gaurdrails

Standalone production scaffold for the PikuAI guardrail pipeline.

This repo keeps:

- `notebooks/` for experiments, dataset work, training, and release validation
- `app/` for production runtime code
- `configs/` for admin-owned policy and routing controls
- `training/` for repeatable scripts
- `tests/` for safety regression coverage

The classifier service exposes one API entrypoint:

- `POST /api/v1/guardrail/classify`

Separate scaffold services now exist at the repo root for future scaling:

- `validator` -> `POST /api/v1/guardrail/validate`
- `chat` -> `POST /api/v1/guardrail/chat`

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
http://localhost:4001/api/v1/guardrail/classify
```

See [docs/architecture.md](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/architecture.md) for the target production design.
