# Synthetic Raw Training Data Expansion Plan

## Summary

Create a synthetic-data authoring package for all 15 `G2` labels, centered on high-quality per-label raw CSVs plus a single `training_data.md` specification. Each generated raw file will live under `pikuai-gaurdrails/data/raw/` and follow the naming pattern `synthetic_data_{G2_LABEL}_{datetime}.csv`. Each per-G2 file will contain both positive rows for the target class and negative or adjacent-class rows in the same file, with a target size of `150+` rows per G2 and strong positive/negative balance to improve discrimination rather than only recall.

Current repo fact: `data/raw` is empty in this workspace except for `.gitkeep`, so this plan does not include analysis of existing manually-authored raw CSV contents. The plan uses the current schema, codebook, and `flag-solution-logic.md` as the source of truth.

## Key Changes

### 1. Add a dataset spec in `training_data.md`

Create `pikuai-gaurdrails/training_data.md` as the authoring contract for all new synthetic raw CSVs.

It should define:

- The required raw CSV schema: `Topic,Question,G1,G2,G2_all,flags,intent_families,intent_phrases,review_status`
- The allowed flag vocabulary only from `flag-solution-logic.md`
- The rule that `flags` must be JSON with boolean values only
- The naming convention: `synthetic_data_{G2_LABEL}_{YYYYMMDD_HHMMSS}.csv`
- The no-duplicate policy:
  - no exact duplicate `Question`
  - no near-duplicate phrasing within the same target file
  - no template-only rewrites that differ by one token
- The balance policy per G2 file:
  - `150+` total rows
  - strong positive majority, but enough adjacent negatives to force class separation
  - target default split for each file: `~75-80%` positives, `~20-25%` negatives/adjacent
- The negative-row policy:
  - negatives stay in the same per-G2 file
  - negatives must be plausible confusers for the target class, not random unrelated easy examples
- The flag-grounding policy:
  - each target file must use flags consistent with the observed flag relationships in `flag-solution-logic.md`
  - flags are evidence, not one-to-one class definitions
  - positives should include multiple valid flag combinations, not one repeated pattern
- The quality policy:
  - child-like phrasing, mixed clarity, mixed directness, mixed context load
  - realistic ambiguity and borderline cases
  - safe labels for negatives must be deliberate and justified
  - avoid synthetic monotony and repetitive lexical scaffolds

### 2. Define per-G2 authoring notes inside `training_data.md`

For each of these labels:

- `UNSAFE_SEXUAL_CONTENT`
- `GROOMING`
- `COERCIVE_CONTROL`
- `VULN_EXPLOIT`
- `SELF_HARM`
- `DANGEROUS`
- `HATE_GROUP`
- `VIOLENCE`
- `PERSONAL_DIRECTION`
- `SAFETY_HAZARD`
- `AMBIGUOUS_RISK`
- `EMOTIONAL`
- `BULLYING`
- `NEUTRAL_FACT`
- `GENERIC_INTENT`

Add a compact note block covering:

- The label intent
- Typical positive patterns
- Required adjacent negative classes to include
- Expected `G1` tendencies
- Relevant flags from the documented raw-flag usage
- Example flag combinations to vary across positives
- Common false-positive traps to include as negatives

The notes must explicitly reflect the documented flag relationships, for example:

- `SELF_HARM` should vary across `direct_intent`, `indirect_intent`, `has_emotional_distress`, `needs_clarification`
- `GROOMING`, `COERCIVE_CONTROL`, and `VULN_EXPLOIT` should intentionally overlap in some rows so the model learns separation
- `VIOLENCE`, `DANGEROUS`, and `SAFETY_HAZARD` should include close confusers
- `NEUTRAL_FACT` and `GENERIC_INTENT` should contain hard negatives that superficially mention risky topics without actually expressing the target risk intent
- `PERSONAL_DIRECTION` should include advisory-seeking prompts across multiple domains, including some that should resolve to other stronger G2 labels instead

### 3. Generate one raw CSV per G2

For each target G2, create one CSV in `data/raw/` using the required naming convention and same-file positive/negative mixing.

Authoring rules for every file:

- The file’s primary target is one G2 label
- Positive rows must have `G2` set to the target label
- `G2_all` should include the target label and any justified co-occurring labels
- Negative rows must exclude the target label from `G2_all`
- Negative rows should be drawn mostly from adjacent classes most likely to be confused with that target
- `flags` should be fully populated as a valid JSON object over the allowed flag vocabulary
- `review_status` should be a stable value such as `approved`
- `intent_families` and `intent_phrases` should be present and consistent with the class/codebook expectations where available

Suggested composition per file:

- `115-125` positive rows
- `30-40` negative or adjacent rows
- at least `4-6` distinct sub-pattern clusters inside positives
- at least `3-5` distinct confuser categories inside negatives

### 4. Include a lightweight coverage summary

Add a short machine-readable or markdown summary alongside authoring work, either inside `training_data.md` or as a separate notes section, listing for each G2:

- total planned rows
- planned positive count
- planned negative count
- primary adjacent negative labels
- primary flags expected in positives
- uniqueness checks to run

This gives a review checklist before normalization and training.

## Public Interfaces and Data Contract

This plan does not require changing runtime or model APIs. It extends the raw authoring contract used by the normalizer.

Authoring contract assumptions:

- CSVs must remain compatible with `training/slm_classifier/source_normalizer.py`
- `flags` must be JSON and contain only known flags
- `G2_all` may be multi-label but must remain author-authored, not inferred during normalization
- no new flag names will be introduced
- file naming under `data/raw` is expanded, but parsing behavior should continue to rely on CSV schema rather than filename semantics

## Test Plan

After files are created, validate them with non-mutating checks and existing normalizer behavior.

Required validation scenarios:

- Every CSV is detected by source discovery
- Every row passes schema detection
- Every row has non-empty `Question`, `G1`, and `G2`
- Every `flags` payload parses as JSON and contains booleans only
- No unknown flags appear
- No exact duplicate `Question` values exist within a file
- No cross-file duplicate `Question` values exist unless intentionally justified and documented
- Every target G2 file contains both positives and negatives
- Negative rows in a target file do not include the target label in `G2_all`
- `G2_all` values use only supported labels
- Normalization can merge all new files into canonical output without rejection

Recommended additional QA checks:

- per-file counts by positive vs negative
- per-file counts by adjacent negative label
- per-file flag frequency table
- spot review of borderline cases for `GROOMING` vs `VULN_EXPLOIT`, `VIOLENCE` vs `DANGEROUS`, `SAFETY_HAZARD` vs `AMBIGUOUS_RISK`, and `NEUTRAL_FACT` vs `GENERIC_INTENT`

## Assumptions and Defaults

- Use `150+` rows per G2 file.
- Keep negatives inside each per-G2 file, not in separate shared files.
- `data/raw` currently has no existing manual CSVs to analyze in this workspace, so the first implementation pass should create new synthetic raw sources from scratch.
- `training_data.md` is the governing spec and should be written before generating CSVs so all later file creation follows one contract.
- The implementation should optimize for hard negatives and adjacent-class separation, not just boosting positive recall.
