# Operations Job

## Local stack

- FastAPI
- PostgreSQL
- Redis
- Qdrant

## Release gate

Before release:

1. Run notebook `09_end_to_end_guardrail_pipeline_eval.ipynb`
2. Review failed cases
3. Update configs, datasets, or model artifacts
4. Re-run regression tests

## Logging

Every pipeline stage writes a structured event into the response audit trail.
Later iterations should persist the same schema into PostgreSQL and forward operational logs to centralized logging.
