# PikuAI Guardrail Architecture

This repo is the standalone guardrail service for PikuAI. It documents one production runtime flow for child-safe input handling, safe response generation, and auditable review.

## Normative documents

The following docs should be treated as normative for gate and prompt behavior:

- [GL-codebook.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/GL-codebook.csv)
- [Contracts.csv](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/Contracts.csv)
- [gl-classifier-gate-engine-reference.md](/Users/ravindrasingh/Documents/AI-Agents/PikuAI/pikuai-gaurdrails/docs/gl-classifier-gate-engine-reference.md)

Role of each document:

- `GL-codebook.csv` defines the dictionary and policy tables for `G1`, `G2`, `G3`, `G4`, guideline semantics, age-policy settings, prompt rules, and checklist expectations.
- `Contracts.csv` defines the stage contract from classifier output to gate engine output to SafetyEnvelope to prompt manager and prompt checklist.
- `gl-classifier-gate-engine-reference.md` explains the intended runtime interpretation of those contracts in prose.

## Runtime Contract

Only one public runtime endpoint exists:

- `POST /api/v1/guardrails/run`

That endpoint owns the whole flow. There are no public per-stage guardrail endpoints in this architecture.

## Architecture Rules

- `notebooks/` are for experimentation, training, evaluation, and release validation only.
- Production runtime logic lives in Python modules under `app/`.
- The SLM is responsible for GL detection and related safety-category evidence only.
- `G1` and `G2` may be exposed as normalized classifier-stage outputs, but they remain deterministic policy-governed values aligned to `GL-codebook.csv` and `Contracts.csv`.
- `G3` and `G4` are derived deterministically from active `G2` values using the codebook gate tables.
- Decision fields and prompt contract values are derived deterministically in backend code and policy configs.
- `PromptContract` is a structured internal object first, and only later rendered into a model-specific prompt string.
- The router selects model, prompt rendering strategy, and generation configuration from the prompt contract.
- Audit storage defaults to structured decision summaries.
- Admin review is an escalation queue, not just passive logging.

## Production Pipeline

The runtime flow is defined in this exact order:

Child Message  
↓  
1. Context Builder  
↓  
2. Input Normalizer  
↓  
3. Rule-Based Safety Filter  
↓  
4. GL Signal Classifier  
↓  
5. Deterministic Gate Mapper (`G1` → `G2` → `G3` → `G4`)  
↓  
6. Policy / Prompt Contract Builder  
↓  
7. LLM Safety Classifier Verifier  
↓  
8. Conversation / Multi-Turn Guard  
↓  
9. RAG / Knowledge Guardrail  
↓  
10. Prompt Contract Renderer + LLM Router  
↓  
11. Child-Safe LLM  
↓  
12. Output Safety Validator  
↓  
13. Safe Rewriter / Fallback  
↓  
14. Audit Log + Admin Review

This stage order is normative. Later stages may consume outputs from earlier stages, but they must not bypass them.

## Stage Intent

### 1. Context Builder

Build request context from the child profile, message, session id, and recent conversation state. This stage gathers the minimum structured context needed for all downstream safety decisions.

### 2. Input Normalizer

Normalize the child input into a consistent internal form before any classifier or rule sees it. This includes whitespace cleanup, punctuation cleanup, language hints, canonical text formatting, and safe preprocessing required before rule or model evaluation.

### 3. Rule-Based Safety Filter

Run deterministic policy checks for terms, patterns, or explicit safety rules that should short-circuit or strongly constrain downstream handling.

### 4. GL Signal Classifier

Run the primary SmolLM2 classifier to detect `GL-01` through `GL-13`. This stage is multi-label signal detection only. It should not directly invent `G1`, `G2`, `G3`, `G4`, or final policy action.

At the end of this stage, the system may attach a normalized classifier output object that includes policy-aligned `G1` and `G2` values for downstream use. Those values should be treated as a deterministic mapping layer attached to classification, not as unconstrained free-form model output.

### 5. Deterministic Gate Mapper

Convert active GL signals into:

- `G1`: broad content nature
- `G2`: framing or intent type
- `G3`: safeguarding severity
- `G4`: final action and response style

More precisely:

- `G1` and `G2` are resolved using the controlled LOV dictionary in `GL-codebook.csv`.
- `G3` is computed deterministically from the active `G2` severity floors and emitted modifiers.
- `G4` is computed deterministically from `G3` plus additive guideline behavior.

This logic is business policy and must stay configurable and auditable against the codebook and contracts docs.

### 6. Policy / Prompt Contract Builder

Convert `G4`, age band, and active signals into:

- `allow_llm`
- `allow_rag`
- `response_mode`
- `risk_level`
- `parent_visible`
- prompt contract JSON

This stage is the policy boundary between classification and generation.

It should also append the age-policy runtime settings from Block I of `GL-codebook.csv`, such as:

- `max_words`
- `depth`
- age-calibrated response style

Age policy must not override `G3` or `G4`. It only shapes the final answer constraints.

### 7. LLM Safety Classifier

Invoke the secondary safety model when the classifier is low-confidence, the case is ambiguous, the content is high-risk, or a second opinion is required for safer adjudication.

### 8. Conversation / Multi-Turn Guard

Evaluate recent context for multi-turn evasion, repeated risky behavior, grooming-style patterns, secrecy reinforcement, or context-dependent escalation.

### 9. RAG / Knowledge Guardrail

Filter retrieval eligibility before knowledge is added to generation. This stage may use the age-understanding outputs, classifier outputs, and conversation-risk markers to restrict or deny retrieval.

Only approved RAG context may pass beyond this stage.

### 10. Prompt Contract Renderer + LLM Router

Render the final model prompt from the structured prompt contract and use it to select the target model and generation strategy.

### 11. Child-Safe LLM

Generate the final answer only after all earlier controls approve generation and the prompt contract has been fully constrained.

### 12. Output Safety Validator

Validate the candidate answer before it is shown. This stage checks:

- content safety
- age-fit explanation quality
- over-detailed explanations
- weak adult-redirection where required
- unsafe phrasing or autonomy framing

### 13. Safe Rewriter / Fallback

Repair unsafe answers when safe rewriting is possible. If the answer cannot be repaired safely, return a deterministic fallback or trusted-adult redirect.

### 14. Audit Log + Admin Review

Capture structured audit events for each stage and create escalation records when review is needed.

Admin review is modeled as an escalation queue, not a passive analytics sink.

## Core Internal Contracts

### GuardrailDecision

A structured internal object used across the runtime. It should include:

- normalized input payload
- GL signal results
- active GL ids
- gate outputs
- decision fields
- prompt contract
- top-level runtime fields such as `policy_bucket`, `response_mode`, `risk_level`, `parent_visible`, and `confidence`

### PromptContract

A structured internal object used to drive both prompt rendering and routing. It must include:

- normalized child message
- child profile and effective age band
- GL signal outputs
- gate outputs
- upstream safety decisions
- conversation-risk markers
- approved RAG context only
- answer constraints
- refusal and redirection rules
- model-routing hints

This object must never include blocked RAG chunks, unsafe hidden instructions, or raw artifacts that policy has already rejected.

### AuditReviewRecord

A structured internal record for auditable review and escalation handling. It should include:

- stage name
- decision or outcome summary
- reason codes
- confidence where applicable
- model identifier where applicable
- whether escalation was created

## Prompt Contract Rules

The prompt contract is built only after the upstream guardrail stages complete. It is the single approved source of truth for generation.

The router reads the prompt contract to determine:

- which model to call
- which rendering format to use for that model
- which generation settings to apply
- whether generation is allowed at all

The child-safe LLM should not infer policy from scratch. It should receive explicit constraints from the prompt contract and the age explanation policy.

Prompt rendering and QA must remain consistent with the prompt rules and checklist documented in `GL-codebook.csv` and `Contracts.csv`. In particular:

- prompt templates must match gate outputs faithfully
- modifier-driven constraints such as `no_content_engagement` and `no_curiosity_invite` must be preserved
- a generated prompt should pass the checklist before LLM execution

## Guardrail Decision JSON

The backend should build a runtime decision object with this shape before generation:

```json
{
  "input": {
    "question": "Who is God?",
    "age_band": "5-8",
    "language": "en",
    "recent_context": "none"
  },
  "gl_signals": {
    "GL-01": {
      "name": "Age-Calibrated Depth",
      "triggered": true,
      "confidence": 0.99,
      "emits": {
        "needs_age_calibration": true,
        "age_band": "5-8"
      }
    },
    "GL-09": {
      "name": "Factual Civic / Religious Detector",
      "triggered": true,
      "confidence": 0.94,
      "emits": {
        "factual_civic_religious": true
      }
    }
  },
  "active_gls": ["GL-01", "GL-09"],
  "gates": {
    "G1": "FACT",
    "G2": "NEUTRAL_FACT",
    "G2_all": ["NEUTRAL_FACT"],
    "G3": "SV0",
    "G4": "ALLOW"
  },
  "decision": {
    "allow_llm": true,
    "allow_rag": false,
    "response_mode": "neutral_age_calibrated_explain",
    "risk_level": "low",
    "parent_visible": false
  },
  "prompt_contract": {
    "age_band": "5-8",
    "tone": "simple_warm_neutral",
    "max_words": 80,
    "depth": "very_simple",
    "must_do": [
      "answer neutrally",
      "acknowledge that people and families may believe different things",
      "use simple words for the child's age"
    ],
    "must_not_do": [
      "rank beliefs",
      "tell the child what to believe",
      "mock any belief"
    ]
  }
}
```

The SLM should not generate this JSON directly. It predicts GL signals, and the backend assembles this object deterministically.

## Config Ownership

These files are the admin-controlled source of truth for policy:

- `configs/guidelines.yaml`
- `configs/gate_mapping.yaml`
- `configs/severity_mapping.yaml`
- `configs/action_mapping.yaml`
- `configs/age_policy.yaml`
- `configs/prompt_contracts.yaml`

Policy changes in these files must not require retraining the GL classifier.

## Training Contract

The canonical GL classifier dataset lives at:

- `data/processed/piku_gl_classifier_train.jsonl`

Raw spreadsheet or export files are placed in:

- `data/raw/`

The training pipeline should detect any raw source that has not yet been converted into the canonical JSONL dataset and record it in:

- `data/processed/piku_gl_classifier_manifest.json`

Classifier training rows should include GL labels plus expected gate outputs for audit and evaluation, but the model objective remains GL detection only.

## Audit and Review Rules

Audit storage defaults to structured decision summaries rather than full raw traces. By default, v1 architecture should not require storing:

- raw prompt text
- raw full model outputs
- raw RAG payloads

Admin review should create an escalation record for cases such as:

- parent-visible events
- high-risk outcomes
- low-confidence outcomes
- validator-failed outputs
- rewritten or fallbacked outputs

## Model Roles

- Primary GL classifier: `HuggingFaceTB/SmolLM2-135M-Instruct`
- Multilingual fallback classifier: `Qwen/Qwen2.5-0.5B-Instruct`
- Safety judge: `meta-llama/Llama-Guard-3-1B`
- Child-safe answer model: `meta-llama/Llama-3.2-1B-Instruct`

## Repository Intent

- `configs/` contains admin-controlled policy state
- `training/` contains repeatable scripts
- `tests/` contains regression and red-team coverage
- `docs/` contains architecture and operating guidance for the production guardrail service

This document is the authoritative architecture reference for the production-grade PikuAI guardrail pipeline.
