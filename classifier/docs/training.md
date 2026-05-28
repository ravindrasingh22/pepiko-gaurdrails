# Training Jobs

## Documentation hierarchy

Training should stay aligned with these design references:

- `docs/GL-codebook.csv`
- `docs/Contracts.csv`
- `docs/gl-classifier-gate-engine-reference.md`

If scripts, notebooks, or examples diverge from those sources, reconcile the docs and runtime contract first rather than letting training drift.

## Current SLM classifier

The active classifier training path is:

- scripts: `classifier/training/slm_classifier/`
- canonical dataset: `classifier/data/processed/piku_gl_classifier_train.jsonl`
- split manifest: `classifier/data/processed/piku_gl_classifier_splits.json`
- model artifact directory: `classifier/models/piku-slm-guardrail-deberta-v3-small/`

The active core model is:

- `deberta` -> `microsoft/deberta-v3-small`

Current training uses a shared-encoder multi-head classifier:

- `G1`: multiclass head
- `G2`: multiclass head
- `flags`: multilabel head
- `intent_families`: multilabel head, only when `train_intent_heads=true`

`G3` and `G4` are not trained. They are derived deterministically at runtime from primary `G2`.

## Dataset contract

The canonical row is normalized from raw CSV/XLSX sources and keeps the training targets the model actually learns:

```json
{
  "sample_id": "belief_001",
  "topic": "Belief & Religion",
  "question": "Who is God?",
  "language": "en",
  "recent_context": "none",
  "g1": "BELIEF",
  "g2": ["NEUTRAL_FACT"],
  "flags": {
    "direct_intent": false,
    "has_personal_direction": false
  },
  "intent_families": [
    "factual_definition",
    "descriptive_what_why_how"
  ],
  "intent_families_present": true
}
```

Important rules:

- training uses only `train` and `test` splits
- the `G2` model target is the primary `G2` only
- `G2_all` is not a training target
- `intent_families` are populated from Block J LOV lookup and may also merge authored values from raw data
- context is an input feature, not a separate target

## Raw source rules

- put candidate spreadsheets or exports in `classifier/data/staging/`
- promote only training-ready files into `classifier/data/raw/`
- `--continuous` rebuilds the canonical dataset from `data/raw/`
- training input discovery is intended to use `data/raw/`, not `data/staging/`

## Input formatting

The current classifier input format is question-first:

```text
Classify the PRIMARY QUESTION for child-safety gating.
Use BACKGROUND CONTEXT only when it changes the meaning of the primary question.
PRIMARY QUESTION: ...
BACKGROUND CONTEXT: ...
```

This is deliberate. The current question is the dominant field and context is secondary.

## Training defaults

Current defaults in code are approximately:

- `epochs=4`
- `batch_size=2`
- `learning_rate=5e-6` for backbone
- `head_learning_rate=5e-5` for classifier heads
- `g1_loss_weight=0.2`
- `g2_loss_weight=2.0`
- `flag_loss_weight=0.3`
- `intent_family_loss_weight=0.15`
- `flag_max_pos_weight=10.0`
- `intent_family_max_pos_weight=10.0`
- `gradient_clip_norm=1.0`
- `train_intent_heads=false`

The repo now supports asymmetric learning rates and separate multilabel `pos_weight` caps for flags vs. intent families.

## Resume behavior

Resume behavior is split into two parts:

- model weights may be reused from existing artifacts
- optimizer state restore is intentionally treated conservatively for compatibility

If `--continuous` rebuilds the dataset and the dataset fingerprint changes:

- model weights may still be reused
- epoch and batch progress reset to the start of training on the rebuilt dataset

## CLI examples

Fresh training:

```bash
cd classifier
python -m training.slm_classifier.train --core deberta --device cpu
```

Rebuild from `data/raw/` and continue from latest compatible weights:

```bash
python -m training.slm_classifier.train \
  --core deberta \
  --continuous \
  --device cpu
```

Two-stage training with asymmetric learning rates:

```bash
python -m training.slm_classifier.train \
  --core deberta \
  --continuous \
  --device cpu \
  --freeze-backbone true \
  --batch-size 12 \
  --learning-rate 1e-5 \
  --head-learning-rate 5e-5 \
  --epochs 4

python -m training.slm_classifier.train \
  --core deberta \
  --device cpu \
  --freeze-backbone false \
  --unfreeze-top-layers 2 \
  --batch-size 16 \
  --learning-rate 5e-6 \
  --head-learning-rate 2e-5 \
  --epochs 4 \
  --resume
```

Training without intent-family backprop:

```bash
python -m training.slm_classifier.train \
  --core deberta \
  --device cpu \
  --train-intent-heads false
```

Training with intent-family head enabled and separate multilabel caps:

```bash
python -m training.slm_classifier.train \
  --core deberta \
  --device cpu \
  --train-intent-heads true \
  --flag-max-pos-weight 8 \
  --intent-family-max-pos-weight 10
```

## Evaluation summary

Training completion currently reports test metrics only:

- `G1` accuracy, macro F1, weighted F1
- `G2` accuracy, macro F1, weighted F1
- flags exact-match accuracy, micro precision, micro recall, micro F1, macro F1
- intent-family exact-match accuracy, micro precision, micro recall, micro F1, macro F1

For the auxiliary heads, precision matters operationally because noisy flags or noisy intent families can pollute downstream tone or policy behavior.
