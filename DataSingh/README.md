# DataSingh Guidelines

`DataSingh` is the data generation and data ingestion workspace for `pikuai-gaurdrails`.

Its job is to create or collect datasets needed by the guardrails stack.

## Responsibilities

- Generate synthetic or prompt-driven data for experiments, evaluation, and training.
- Pull curated external datasets when the source is trusted and relevant.
- Normalize output into a consistent local format before downstream use.
- Keep a clear record of where each dataset came from.

## Folder Rules

- `curated/` is the only destination for generated or pulled datasets.
- `prompts/` stores prompt templates or prompt specifications used for synthetic generation.
- Do not write generated files at repo root or inside unrelated app folders.

## Output Rules

- Every generated or pulled artifact must be saved under `DataSingh/curated/`.
- Prefer JSONL, JSON, or CSV depending on the dataset shape.
- Each artifact should include source metadata when possible:
  - generation mode
  - created timestamp
  - source dataset or prompt name
  - schema/version notes

## Supported Data Modes

### 1. Prompt-based generation

Use this when records are authored from instructions, templates, or LLM prompts.

Examples:

- safety prompts
- policy edge cases
- red-team conversations
- rubric-based examples

Store prompt templates under `prompts/` and save the resulting dataset under `curated/`.

### 2. Hugging Face pull

Use this when a public dataset should be copied locally for curation or transformation.

Examples:

- benchmark datasets
- moderation datasets
- safety-aligned dialogue sets

The pulled output still lands in `curated/` after local conversion or filtering.

## Workflow

1. Define the source:
   - prompt file, inline prompt, or Hugging Face dataset id
2. Run the DataSingh Python app
3. Write the resulting dataset into `DataSingh/curated/`
4. Review and rename the artifact clearly
5. Promote or transform it elsewhere only after curation

## Naming Guidance

Prefer names like:

- `policy_edges_v1.jsonl`
- `hf_openai_moderation_eval_subset.csv`
- `lov_prompt_batch_2026_05_23.json`

Keep names descriptive and versionable.

## App Entry Point

Use `DataSingh/datasingh_app.py` to generate or pull datasets.

Examples:

```bash
python DataSingh/datasingh_app.py prompt --prompt-name safety_cases --count 20
python DataSingh/datasingh_app.py hf --dataset-id some-org/some-dataset --split train
```

## Local Ollama Term Curation

Use the `curate-terms` command to generate real-world usage rows from your local Ollama model.

What it does:

- reads unprocessed rows from `DataSingh/master-terms.csv`
- sends terms to your local Ollama model in batches
- writes generated rows into `DataSingh/curated/datasingh_{model}_{date}.csv`
- stores only `term,text` in the curated CSV
- marks completed terms as `yes` in `master-terms.csv`
- resumes from the next uncurated term on the next run

Recommended first run with `mistral`:

```bash
python DataSingh/datasingh_app.py curate-terms --model mistral --term-limit 20 --min-examples 5 --max-examples 10
```

Useful flags:

- `--model mistral`
- `--term-limit 20`
- `--min-examples 5`
- `--max-examples 10`
- `--ollama-host http://localhost:11434`

Runtime behavior:

- the CLI sends one term per Ollama call
- it prints the term being processed
- it prints the exact prompt
- it prints the raw model output before validation

Requirements:

- Ollama must be running locally
- the model must already exist locally, for example `mistral`

Example Ollama startup:

```bash
ollama serve
ollama run mistral
```
