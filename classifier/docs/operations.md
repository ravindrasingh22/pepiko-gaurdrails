# Operations Job

## Local stack

- FastAPI
- PostgreSQL
- Redis
- Qdrant

## Release gate

Before a release:

1. Rebuild canonical data from `classifier/data/raw/` if raw inputs changed.
2. Run classifier training or evaluation for the active `deberta` artifact.
3. Review test metrics, especially:
   - `G2` macro F1
   - flag precision / recall
   - intent-family precision / recall when enabled
4. Review classifier inference spot checks for prompt tone drift and flag overfiring.
5. Re-run regression tests.

## Classifier operational notes

- active training split is `train` + `test`
- active production core is `deberta`
- `--continuous` rebuilds data and reuses compatible model weights
- if dataset fingerprint changes, epoch/batch resume progress resets
- optimizer-state resume should be treated conservatively after architecture changes

## Logging

Every pipeline stage should write a structured event into the response audit trail.

For classifier training, operationally useful fields include:

- selected device
- backbone LR
- head LR
- `train_intent_heads`
- `flag_max_pos_weight`
- `intent_family_max_pos_weight`
- final test metrics

Later iterations can persist the same schema into PostgreSQL and forward operational logs to centralized logging.
