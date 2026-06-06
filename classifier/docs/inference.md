# Inference Contract

## Active Runtime Path

The active classifier runtime uses the trained SLM artifact in:

- `classifier/models/piku-slm-guardrail-deberta-v3-small/`

The active core model is:

- `deberta` -> `microsoft/deberta-v3-small`

Inference must use an artifact with:

- `cross_feature_fusion_version >= 3`

Artifacts trained before cross-attention GLU feature fusion are rejected and must be retrained.

## Input Rendering

The classifier receives one rendered text sequence:

```text
Classify the PRIMARY QUESTION for child-safety gating.
Use BACKGROUND CONTEXT only when it changes the meaning of the primary question.
PRIMARY QUESTION: ...
BACKGROUND CONTEXT: ...
```

The primary question is dominant. Context is included only as disambiguating evidence.

## Pattern Extraction

Before the G2 head is evaluated, runtime builds deterministic prior vectors from the question and context:

- `intent_rule_features`: binary vector ordered by the `intent_families` vocabulary
- `phrase_trigger_features`: 15-dimensional vector ordered by the G2 LOV vocabulary

Phrase extraction uses the same resilient matcher as training:

- normalized substring fast path
- punctuation and contraction normalization
- unordered token-set fallback
- edit distance `<= 1` for tokens longer than three characters
- exact matching for short tokens
- ordered wildcard matching for placeholder `X` tokens against targeted noun/pronoun slots

Matcher outputs are cached by normalized text to keep inference overhead bounded.

## Model Pass

The trained model uses a shared DeBERTa encoder with masked mean pooling over `last_hidden_state`.

The pooled embedding feeds:

- `G1` multiclass head
- `flags` multilabel head
- `intent_families` multilabel head
- `intent_phrases` multilabel head
- G2 cross-attention GLU fusion head

For G2, runtime combines:

- pooled DeBERTa embedding
- learned intent-family probabilities
- deterministic intent-family rule activations
- deterministic 15-D G2 phrase-trigger activations

Gold intent-family labels are never injected at inference. The fusion path uses learned probabilities plus deterministic runtime rule matches only.

## Cross-Attention GLU Fusion

`CrossFeatureFusionHead` uses single-head `nn.MultiheadAttention`:

- query: mean-pooled DeBERTa embedding
- keys and values: projected intent-rule token and projected phrase-trigger token

The attended prior is concatenated with the pooled embedding and passed through a GLU-style projection. The gated prior is added back to the pooled embedding, layer-normalized, and classified into primary G2 logits.

## Output Contract

The active classifier returns:

- primary `G1`
- primary `G2`
- high-confidence `flags`
- high-confidence `intent_families`
- high-confidence `intent_phrases` in debug/internal output
- optional score maps in internal/debug output

`G2_all` is not part of the active runtime classifier or gate-engine contract. `G3` and `G4` are derived deterministically from primary `G2` and policy configuration.

## Thresholds

The default threshold is `0.8` unless a CLI or caller explicitly overrides it.

The threshold applies to:

- multilabel flags
- learned intent-family activations
- learned intent-phrase activations

Primary `G2` is selected from the G2 logits as the primary class. Auxiliary evidence may support or explain the decision, but it does not replace the trained G2 head.
