# Training Jobs

## Documentation hierarchy

Training must stay aligned with these documentation artifacts:

- [GL-codebook.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/GL-codebook.csv): normative dictionary for `G1`, `G2`, `G3`, `G4`, guideline semantics, age policy, and prompt authoring constraints.
- [Contracts.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/Contracts.csv): stage-by-stage contract showing how classifier output flows into gate engine, SafetyEnvelope, prompt manager, and prompt checklist.
- [gl-classifier-gate-engine-reference.md](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/gl-classifier-gate-engine-reference.md): prose interpretation of the two CSVs and the recommended runtime split of responsibilities.

These three docs should be treated as the primary design references for training labels and runtime contract expectations. If notebooks, scripts, or examples diverge from them, the docs should be reconciled first rather than letting training drift.

## SLM GL classifier

- Objective: train SmolLM2 to detect `GL-01` through `GL-13` as a multi-label classifier.
- Notebooks: `02_guardrail_dataset_builder.ipynb`, `03_slm_classifier_train_smolLM2_135M.ipynb`, `04_slm_classifier_eval_thresholds.ipynb`
- Scripts: `training/slm_classifier/`
- Canonical dataset target: `data/processed/piku_gl_classifier_train.jsonl`
- Source discovery manifest: `data/processed/piku_gl_classifier_manifest.json`
- Model output target: `models/piku-slm-guardrail-smollm2-135m/`

### Responsibility split

The intended split is:

- The classifier stage detects `GL-01` to `GL-13`.
- The classifier stage also assigns `G1` and `G2`.
- `G3` and `G4` are deterministic gate-engine outputs derived from `G2` definitions in `GL-codebook.csv`.
- Age policy is runtime context only. It must not change classifier labels, `G3` severity, or `G4` action.

This means training should not treat age as a reason to alter safety category assignment. Age only changes downstream answer constraints such as `max_words`, `depth`, and style.

### Canonical classifier row

```json
{
  "sample_id": "religion_001_5_8",
  "question": "Who is God?",
  "age_band": "5-8",
  "language": "en",
  "recent_context": "none",
  "gl_01": 1,
  "gl_02": 0,
  "gl_03": 0,
  "gl_04": 0,
  "gl_05": 0,
  "gl_06": 0,
  "gl_07": 0,
  "gl_08": 0,
  "gl_09": 1,
  "gl_10": 0,
  "gl_11": 0,
  "gl_12": 0,
  "gl_13": 0,
  "g1": "BELIEF",
  "g2": "NEUTRAL_FACT",
  "g3": "SV0",
  "g4": "ALLOW"
}
```

### Source-of-truth rules

- Put raw spreadsheets or exports in `data/raw/`.
- Any file in `data/raw/` that does not start with `trained_` is treated as pending input for the dataset builder.
- The training pipeline writes a manifest so unfinished sources are easy to detect before training.
- Do not use generated prompts or model answers as classifier inputs.
- Authoring sheets may stay wide and human-friendly, but training ingestion must flatten them to:
  `sample_id, question, age_band, language, recent_context, gl_01..gl_13, g1, g2, g3, g4`
- For `docs/Religion-politics-idealogy.csv`, create one training row per `question x age_band`.
- Keep age-specific reference answers only as optional audit columns; they are not classifier inputs.
- `GL-codebook.csv` is the canonical dictionary for allowed LOV ids, severity floors, modifier semantics, and age runtime settings.
- `Contracts.csv` is the canonical contract for how classifier-stage outputs are consumed by the gate engine, SafetyEnvelope builder, prompt manager, and prompt checklist.

### Training split of responsibility

- Model training learns or predicts `GL`, `G1`, and `G2`.
- `G1` and `G2` must remain consistent with the LOV dictionary and classifier notes in `GL-codebook.csv`.
- `G3`, `G4`, response decisions, and prompt contracts are derived deterministically from configs and codebook-driven policy.
- Prompt templates and checklist logic must not be folded into model training. They belong to prompt-management policy, not classifier learning.

### Normalization guidance

Before any classifier inference or training feature extraction:

- normalize whitespace and punctuation
- preserve the canonical question text
- preserve language hints
- avoid age-conditioned preprocessing
- avoid introducing prompt text, answer text, or other generation artifacts into classifier inputs

The classifier must see the question as a classification problem, not as a response-generation problem.

## Child-safe answer LLM

- Notebook ownership: `05`, `06`, `07`
- Script ownership: `training/childsafe_llm/`
- Output target: `models/piku-childsafe-llm-lora/`

## RAG safety tagger

- Notebook ownership: `08`
- Script ownership: `training/rag_tagger/`
- Output target: future chunk tagger model or metadata pipeline
