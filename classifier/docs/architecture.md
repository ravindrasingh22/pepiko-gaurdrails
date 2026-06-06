# PikuAI Guardrail Architecture

This repo is the standalone guardrail service for PikuAI. It documents the current runtime flow for child-safe input handling, safe response generation, and auditable review.

## Normative Configuration

Executable classifier configuration is loaded from:

- `configs/codebook-config/*.yaml`

These documents remain policy references:

- `docs/GL-codebook.csv` (reference document only)
- `docs/Contracts.csv`
- `docs/gl-classifier-gate-engine-reference.md`

## Current classifier architecture

The active SLM classifier is a shared-encoder multi-head DeBERTa model:

- backbone: `microsoft/deberta-v3-small`
- pooling: masked mean pooling over `last_hidden_state`
- pattern priors:
  - resilient intent-family rule vector
  - 15-dimensional G2 phrase-trigger vector
- G2 fusion: single-head cross-attention where the pooled DeBERTa embedding queries projected intent and phrase prior tokens, followed by GLU-style gated residual fusion
- heads:
  - `g1_classifier`: multiclass
  - `g2_classifier`: multiclass primary `G2`
  - `flag_classifier`: multilabel
  - `intent_family_classifier`: multilabel, optional in training
  - `intent_phrase_classifier`: multilabel, optional in training

This is a hard-parameter-sharing design: one encoder, multiple task heads.

## Runtime contract

Only one public runtime endpoint exists:

- `POST /api/v1/guardrail/classify`

The endpoint owns the whole flow. There are no public per-stage production endpoints.

## Architecture rules

- notebooks are for experimentation and validation only
- production runtime logic lives under `classifier/app/`
- the classifier stage assigns:
  - `G1`
  - primary `G2`
  - auxiliary `flags`
  - auxiliary `intent_families`
- `G3` and `G4` are derived deterministically from primary `G2`
- `G2_all` is no longer part of the active inference or gate-engine contract
- prompt contracts, routing, and answer policy remain deterministic backend behavior

## Runtime pipeline

The runtime flow is:

1. Context builder
2. Input normalizer
3. Rule-based safety filter
4. SLM / heuristic classifier
5. Deterministic gate mapper
6. Policy / prompt contract builder
7. LLM safety verifier
8. Conversation / multi-turn guard
9. RAG guardrail
10. Prompt renderer + model router
11. Child-safe LLM
12. Output safety validator
13. Safe rewriter / fallback
14. Audit log + admin review

This order is normative.

## Classifier input

The current text classifier sees one rendered input string, not separate structured channels:

```text
Classify the PRIMARY QUESTION for child-safety gating.
Use BACKGROUND CONTEXT only when it changes the meaning of the primary question.
PRIMARY QUESTION: ...
BACKGROUND CONTEXT: ...
```

That means context is part of the text sequence, but the format intentionally makes the question dominant.

## Classifier outputs

The active classifier decision path uses:

- `G1` from the `G1` head
- primary `G2` from the cross-attention GLU fusion `G2` head
- `flags` as auxiliary evidence
- `intent_families` as auxiliary evidence
- `intent_phrases` as auxiliary/internal evidence

The active gate engine uses primary `G2`, not `G2_all`.

`intent_families` and `intent_phrases` are currently useful mainly as:

- auxiliary supervision during training
- metadata/supporting inference output

They are not currently the direct runtime decision driver.

## Deterministic gate mapping

The runtime derives:

- `G3_SV`: safeguarding severity
- `G3_MOD`: modifier tags
- `G3_FORWARD`: the exact `(G3_SV, G3_MOD)` packet passed to Gate 4
- `G4`: final action, ending, and response style

from primary `G2` and policy configuration.

Classifier prediction order:

- `G1`, primary `G2`, and `flags` are predicted by the classifier/runtime classifier layer.
- Block B config defines each `G2` severity floor and emitted modifier tags.
- Block C computes `G3_SV`, `G3_MOD`, and `G3_FORWARD`.
- Block D reads `G3_FORWARD`: `G3_SV` selects the base action row, then `G3_MOD` applies modifier variants such as clarification, hard block, escalation, or style changes.

Age policy is runtime context only. It must not change classifier labels or override `G3` / `G4`.

## Prompt contract

The prompt contract is a structured backend object. It is built only after guardrail stages complete and is the single approved source of truth for generation constraints.

It should include:

- normalized child message
- age band
- `G1`
- primary `G2`
- deterministic `G3_SV`, `G3_MOD`, and `G3_FORWARD`
- deterministic `G4` action, ending, and style
- `codebook_flow` showing classifier output -> Block B -> Block C -> Block D
- approved RAG context only
- answer constraints
- routing hints

The final rendered prompt is based on this contract. The child-safe LLM should follow the supplied `G4` behavior and must not infer policy from scratch or recompute gate outcomes.

## Training contract

The canonical training dataset lives at:

- `classifier/data/processed/piku_gl_classifier_train.jsonl`

Raw sources are promoted into:

- `classifier/data/raw/`

Training uses:

- `train` split
- `test` split

The model learns:

- `G1`
- primary `G2`
- `flags`
- `intent_families` when enabled
- `intent_phrases` when enabled

The model does not learn:

- `G3`
- `G4`
- `G2_all`

## Inference modes

Two classifier-facing modes are relevant:

- `slm_pure`
  - model-only classifier output
  - returns primary `G1`, primary `G2`, `flags`, `intent_families`, and internal phrase evidence
- `slm`
  - model-backed runtime classifier path
  - still returns primary `G1`, primary `G2`, `flags`, `intent_families`, and internal phrase evidence
  - then flows into deterministic gate and policy logic

## Audit and review

Audit storage should prefer structured decision summaries over raw internal traces.

Admin review is an escalation queue, not passive analytics.
