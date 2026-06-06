# Training Jobs

## Documentation hierarchy

Executable classifier configuration is loaded from:

- `configs/codebook-config/*.yaml`

Training should also stay aligned with these design references:

- `docs/GL-codebook.csv` (reference document only)
- `docs/Contracts.csv`
- `docs/gl-classifier-gate-engine-reference.md`

If scripts, notebooks, or examples diverge from those sources, reconcile the docs and runtime contract first rather than letting training drift.

## Current SLM classifier

The active classifier training path is:

- scripts: `classifier/training/slm_classifier/`
- canonical dataset shards: `classifier/data/processed/piku_gl_classifier_train/part-*.jsonl`
- split manifest: `classifier/data/processed/piku_gl_classifier_splits.json`
- model artifact directory: `classifier/models/piku-slm-guardrail-deberta-v3-small/`

The active core model is:

- `deberta` -> `microsoft/deberta-v3-small`

Current training uses a shared-encoder multi-head classifier:

- `intent_rule_features`: dense binary intent-family rule vector derived from phrase matches
- `phrase_trigger_features`: dense 15-slot vector indicating phrase matches for each G2 LOV
- masked mean pooling over DeBERTa `last_hidden_state`
- `CrossFeatureFusionHead`: G2-only single-head cross-attention plus GLU fusion over pooled text, intent rules, and phrase triggers
- `G1`: multiclass head
- `G2`: multiclass head
- `flags`: multilabel head
- `intent_families`: multilabel head, only when `train_intent_heads=true`
- `intent_phrases`: multilabel head, only when `train_intent_heads=true`

`G3` and `G4` are not trained. They are derived deterministically at runtime from primary `G2`.

## Dataset contract

The canonical row is normalized from raw CSV/XLSX sources and keeps the training targets the model actually learns:

```json
{
  "sample_id": "belief_001",
  "question": "Who is God?",
  "context": "",
  "g1": "BELIEF",
  "g2": ["NEUTRAL_FACT"],
  "flags": {
    "has_emotional_distress": false,
    "has_ambiguous_risk": false
  },
  "intent_families": [
    "factual_definition",
    "descriptive_what_why_how"
  ],
  "intent_families_present": true,
  "intent_phrases": ["what is", "why does X happen"],
  "intent_phrases_present": true
}
```

Important rules:

- training uses only `train` and `test` splits
- the `G2` model target is the primary `G2` only
- `G2_all` is not a training target
- `intent_families` are populated from `configs/codebook-config/intent-lexicon.yaml` and may also merge authored values from raw data
- `intent_phrases` are populated from `configs/codebook-config/intent-lexicon.yaml` and may also merge authored values from raw data
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

Before the G2 classifier runs, the normalizer checks the question and context against the codebook phrases and syntactic intent patterns. Resilient matches produce:

- a binary intent-family rule vector ordered by the `intent_families` vocabulary
- a 15-dimensional phrase-trigger vector ordered by the G2 LOV vocabulary

Phrase extraction uses a resilient two-stage matcher:

- fast path: normalized substring matching
- fallback: punctuation and contraction normalization, unordered token-set matching, and edit distance `<= 1` for tokens longer than three characters

Placeholder `X` tokens in codebook phrases are treated as ordered wildcard slots, not dropped from the fallback token set. The wildcard currently matches targeted noun/pronoun-style tokens such as children, people, classmates, adults, parents, and common pronouns. Compiled token footprints, wildcard regexes, and normalized-text match results are cached to keep runtime overhead bounded. Short tokens still require exact matches to reduce accidental activations.

Intent-family and phrase vocabularies are seeded from the complete codebook before authored-row extensions are appended. Their dimensions therefore remain stable when a refreshed dataset happens to omit examples for a valid codebook rule.

The supervised intent-family head predicts the codebook intent-family probabilities from the pooled DeBERTa representation. Those probabilities are merged with deterministic family-rule activations, then passed into the `CrossFeatureFusionHead` alongside the 15-dimensional G2 phrase-trigger vector. The fusion head projects the intent-rule and phrase-trigger vectors into the encoder hidden space, treats them as two prior tokens, and uses a single-head cross-attention layer where the pooled DeBERTa embedding is the query and the prior tokens are the keys and values. The attended prior then passes through a GLU-style projection before the residual representation is layer-normalized and classified into G2 logits.

Gold intent-family labels supervise the family head but are not passed directly into fusion because they are unavailable during inference. This keeps training and runtime behavior aligned while allowing family supervision to shape G2 logits through the learned family probabilities.

This changes the G2 head architecture. Models trained before cross-attention GLU feature fusion must be retrained before inference.

## Training defaults

Current defaults in code are approximately:

- `epochs=4`
- `batch_size=12`
- `learning_rate=5e-6` for backbone
- `head_learning_rate=5e-5` for classifier heads
- `g1_loss_weight=0.2`
- `g2_loss_weight=2.0`
- `flag_loss_weight=0.3`
- `intent_family_loss_weight=0.15`
- `intent_phrase_loss_weight=0.10`
- `flag_max_pos_weight=8.0`
- `intent_family_max_pos_weight=18.0`
- `intent_phrase_max_pos_weight=18.0`
- `g2_focal_gamma=2.0`
- `intent_family_focal_gamma=2.0`
- `intent_phrase_focal_gamma=2.0`
- `gradient_clip_norm=1.0`
- `train_intent_heads=true`
- `cross_feature_fusion_version=3`
- `local_files_only=true`

The repo now supports asymmetric learning rates and separate multilabel `pos_weight` caps for flags, intent families, and intent phrases.

G2, intent-family, and intent-phrase losses use float32 focal modulation. The `(1 - p_t) ** gamma` multiplier suppresses repetitive easy examples while retaining a strong gradient for incorrect G2 classes and missed sparse family or phrase targets. Probability terms are computed from stable log-softmax or log-sigmoid functions and clamped before exponentiation for MPS-safe behavior. Flags intentionally remain standard BCE.

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
- intent-phrase exact-match accuracy, micro precision, micro recall, micro F1, macro F1

For the auxiliary heads, precision matters operationally because noisy flags, intent families, or intent phrases can pollute downstream tone or policy behavior.
