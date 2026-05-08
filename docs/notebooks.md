# Notebook Plan

The notebook set is intentionally compact. Each notebook should be explicit about inputs, outputs, and the production module it feeds.

## Current set

- `00_environment_check.ipynb`
- `01_policy_taxonomy_builder.ipynb`
- `02_guardrail_dataset_builder.ipynb`
- `03_slm_classifier_train_smolLM2_135M.ipynb`
- `04_slm_classifier_eval_thresholds.ipynb`
- `05_childsafe_llm_dataset_builder.ipynb`
- `06_childsafe_llm_lora_train.ipynb`
- `07_childsafe_llm_eval_redteam.ipynb`
- `08_rag_safety_tagger_eval.ipynb`
- `09_end_to_end_guardrail_pipeline_eval.ipynb`

The runtime logic must stay in Python modules, not inside notebooks.

## Notebook intent

- `00_environment_check.ipynb`: verify Python, model, and storage prerequisites.
- `01_policy_taxonomy_builder.ipynb`: inspect and refine GL definitions plus gate mappings before they are frozen into YAML.
- `02_guardrail_dataset_builder.ipynb`: convert spreadsheet rows into the canonical `piku_gl_classifier_train.jsonl` format and write the pending-source manifest.
- `03_slm_classifier_train_smolLM2_135M.ipynb`: train the GL detector only, not the gate logic.
- `04_slm_classifier_eval_thresholds.ipynb`: calibrate per-GL thresholds and verify precision/recall tradeoffs.
- `05_childsafe_llm_dataset_builder.ipynb`: prepare answer-generation data after guardrail classification is stable.
- `06_childsafe_llm_lora_train.ipynb`: train the child-safe answer model using prompt contracts, not raw spreadsheet prompts.
- `07_childsafe_llm_eval_redteam.ipynb`: validate answer safety on red-team cases.
- `08_rag_safety_tagger_eval.ipynb`: evaluate retrieval gating and chunk-safety behavior.
- `09_end_to_end_guardrail_pipeline_eval.ipynb`: validate `normalizer -> GL detection -> gate mapping -> decision -> prompt contract -> answer -> validator`.

## Clarity requirements

- Start each notebook with the source paths it reads and the artifacts it writes.
- Show the canonical row schema before transformations.
- Separate exploratory cells from production-equivalent logic.
- Link every notebook stage back to the Python module that owns runtime behavior.
