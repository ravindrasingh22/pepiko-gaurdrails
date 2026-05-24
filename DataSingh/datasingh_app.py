from __future__ import annotations

import argparse
import csv
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parent
DATASINGH_DIR = ROOT
CURATED_DIR = DATASINGH_DIR / "curated"
MASTER_TERMS_PATH = DATASINGH_DIR / "master-terms.csv"


def ensure_curated_dir() -> None:
    CURATED_DIR.mkdir(parents=True, exist_ok=True)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_date_stamp() -> str:
    return datetime.now().strftime("%Y_%m_%d")


def sanitize_model_name(model: str) -> str:
    cleaned = model.strip().lower().replace(":", "_").replace("/", "_")
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in cleaned)


def normalize_term_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def example_mentions_term(example: str, term: str) -> bool:
    raw_term = term.strip().lower()
    raw_example = example.strip().lower()
    if raw_term and raw_term in raw_example:
        return True

    normalized_term = normalize_term_key(term)
    normalized_example = normalize_term_key(example)
    if normalized_term and normalized_term in normalized_example:
        return True

    return False


def build_prompt_records(prompt_name: str, count: int, seed_text: str | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index in range(count):
        records.append(
            {
                "id": f"{prompt_name}-{index + 1}",
                "prompt_name": prompt_name,
                "seed_text": seed_text or "",
                "text": f"Sample record {index + 1} for prompt '{prompt_name}'",
                "created_at": utc_timestamp(),
                "source": "prompt",
            }
        )
    return records


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        write_json(path.with_suffix(".json"), [])
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_manifest_for_output(output_path: Path, metadata: dict[str, Any]) -> None:
    manifest_path = output_path.with_name(f"{output_path.stem}_manifest.json")
    write_json(manifest_path, metadata)


def chunked(items: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def load_master_terms() -> list[dict[str, str]]:
    with MASTER_TERMS_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def save_master_terms(rows: list[dict[str, str]]) -> None:
    with MASTER_TERMS_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["term", "category", "data_curated"])
        writer.writeheader()
        writer.writerows(rows)


def append_rows_to_csv(path: Path, rows: list[dict[str, str]]) -> None:
    write_header = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["term", "text"])
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def build_curate_terms_prompt(
    terms: list[dict[str, str]],
    min_examples: int,
    max_examples: int,
) -> str:
    lines = [
        "Generate real-world usage examples for profanity or taboo terms.",
        "Return strict JSON only.",
        "Do not explain the terms.",
        "Do not write dictionary definitions.",
        "Do not write placeholders or framed descriptions like 'someone said TERM'.",
        "Write direct natural utterances, quotes, captions, chat messages, insults, taunts, or explicit statements.",
        "Each example must actually use the term text.",
        "Keep the term field exactly identical to the provided input term.",
        "Do not censor, rename, sanitize, expand, or normalize the term.",
        f"Produce between {min_examples} and {max_examples} examples for each term.",
        "Return JSON in this shape:",
        '{"items":[{"term":"...", "examples":["...", "..."]}]}',
        "Terms:",
    ]
    for row in terms:
        lines.append(f'- term: {row["term"]} | category: {row["category"]}')
    return "\n".join(lines)


def build_single_term_retry_prompt(
    term: str,
    category: str,
    min_examples: int,
    max_examples: int,
) -> str:
    return "\n".join(
        [
            "Generate real-world usage examples for one profanity or taboo term.",
            "Return strict JSON only.",
            f'The term is exactly: {term}',
            f"The category is: {category}",
            "Use the exact term string in every example exactly as written.",
            "Do not explain the term.",
            "Do not define the term.",
            "Do not sanitize or paraphrase the term.",
            "Do not use placeholders or framed descriptions.",
            "Write direct utterances, captions, quotes, insults, chat lines, or explicit statements.",
            f"Return between {min_examples} and {max_examples} examples.",
            'Return JSON in this shape: {"items":[{"term":"...", "examples":["...", "..."]}]}',
        ]
    )


def parse_json_payload(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(text[start:end + 1])


def call_ollama_chat(model: str, prompt: str, host: str, timeout_seconds: int) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "stream": False,
        "format": "json",
        "options": {
            "temperature": 0.7,
        },
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{host.rstrip('/')}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise SystemExit(
            f"Ollama request timed out after {timeout_seconds} seconds at {host}. "
            "Try a higher --timeout-seconds value."
        ) from exc
    except socket.timeout as exc:
        raise SystemExit(
            f"Ollama socket timed out after {timeout_seconds} seconds at {host}. "
            "Try a higher --timeout-seconds value."
        ) from exc
    except error.URLError as exc:
        raise SystemExit(f"Failed to reach Ollama at {host}: {exc}") from exc


def normalize_generated_rows(
    batch_terms: list[dict[str, str]],
    response_payload: dict[str, Any],
    min_examples: int,
    max_examples: int,
) -> list[dict[str, str]]:
    content = response_payload.get("message", {}).get("content", "")
    parsed = parse_json_payload(content)
    generated_items = parsed.get("items", [])
    examples_by_term: dict[str, list[str]] = {}
    examples_by_normalized_term: dict[str, list[str]] = {}
    for item in generated_items:
        term = str(item.get("term", "")).strip()
        examples = [
            str(example).strip()
            for example in item.get("examples", [])
            if str(example).strip()
        ]
        if term:
            examples_by_term[term] = examples
            examples_by_normalized_term[normalize_term_key(term)] = examples

    rows: list[dict[str, str]] = []
    missing_terms: list[str] = []
    for term_row in batch_terms:
        term = term_row["term"]
        normalized_term = normalize_term_key(term)
        examples = examples_by_term.get(term, []) or examples_by_normalized_term.get(normalized_term, [])
        matching_examples = [
            example for example in examples if example_mentions_term(example, term)
        ]
        if len(matching_examples) >= min_examples:
            examples = matching_examples
        if len(examples) < min_examples:
            missing_terms.append(term)
            continue
        trimmed = examples[:max_examples]
        for text in trimmed:
            rows.append({"term": term, "text": text})

    if missing_terms:
        raise SystemExit(
            "Ollama response did not return enough examples for terms: "
            + ", ".join(missing_terms)
        )
    return rows


def generate_rows_for_single_term(
    term_row: dict[str, str],
    args: argparse.Namespace,
) -> list[dict[str, str]]:
    print(f'[datasingh] processing term={term_row["term"]} category={term_row["category"]}')
    prompt = build_single_term_retry_prompt(
        term=term_row["term"],
        category=term_row["category"],
        min_examples=args.min_examples,
        max_examples=args.max_examples,
    )
    print("[datasingh] prompt:")
    print(prompt)
    response_payload = call_ollama_chat(
        model=args.model,
        prompt=prompt,
        host=args.ollama_host,
        timeout_seconds=args.timeout_seconds,
    )
    raw_content = response_payload.get("message", {}).get("content", "")
    print("[datasingh] raw model output:")
    print(raw_content)
    return normalize_generated_rows(
        batch_terms=[term_row],
        response_payload=response_payload,
        min_examples=args.min_examples,
        max_examples=args.max_examples,
    )


def command_curate_terms(args: argparse.Namespace) -> int:
    ensure_curated_dir()
    master_rows = load_master_terms()
    pending = [row for row in master_rows if row.get("data_curated", "").strip().lower() != "yes"]
    if not pending:
        print("All terms are already marked as curated.")
        return 0

    selected = pending[:args.term_limit] if args.term_limit else pending
    output_path = CURATED_DIR / f"datasingh_{sanitize_model_name(args.model)}_{local_date_stamp()}.csv"

    failed_terms: list[str] = []
    for term_row in selected:
        try:
            single_rows = generate_rows_for_single_term(term_row=term_row, args=args)
        except SystemExit:
            failed_terms.append(term_row["term"])
            print(f'[datasingh] failed term={term_row["term"]}')
            continue

        append_rows_to_csv(output_path, single_rows)
        for row in master_rows:
            if row["term"] == term_row["term"]:
                row["data_curated"] = "yes"
        save_master_terms(master_rows)
        print(f'[datasingh] curated term={term_row["term"]} rows={len(single_rows)} output={output_path}')

    if failed_terms:
        print(
            "Some terms were skipped because Ollama did not return enough valid examples: "
            + ", ".join(failed_terms)
        )
    return 0


def command_prompt(args: argparse.Namespace) -> int:
    ensure_curated_dir()
    records = build_prompt_records(
        prompt_name=args.prompt_name,
        count=args.count,
        seed_text=args.seed_text,
    )
    payload = {
        "metadata": {
            "mode": "prompt",
            "prompt_name": args.prompt_name,
            "count": args.count,
            "created_at": utc_timestamp(),
        },
        "records": records,
    }
    output_path = CURATED_DIR / args.output
    write_json(output_path, payload)
    write_manifest_for_output(output_path, payload["metadata"])
    print(f"Wrote prompt dataset to {output_path}")
    return 0


def command_hf(args: argparse.Namespace) -> int:
    ensure_curated_dir()
    try:
        from datasets import load_dataset
    except ImportError:
        raise SystemExit(
            "Missing dependency: install 'datasets' to use Hugging Face pulls."
        )

    dataset = load_dataset(args.dataset_id, args.config_name, split=args.split)
    if args.limit is not None:
        dataset = dataset.select(range(min(args.limit, len(dataset))))

    rows = [dict(row) for row in dataset]
    metadata = {
        "mode": "huggingface",
        "dataset_id": args.dataset_id,
        "config_name": args.config_name,
        "split": args.split,
        "row_count": len(rows),
        "created_at": utc_timestamp(),
    }

    output_path = CURATED_DIR / args.output
    if output_path.suffix.lower() == ".csv":
        write_csv(output_path, rows)
        write_manifest_for_output(output_path, metadata)
    else:
        write_json(output_path, {"metadata": metadata, "records": rows})

    print(f"Wrote Hugging Face dataset to {output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate or pull datasets into DataSingh/curated."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prompt_parser = subparsers.add_parser("prompt", help="Create prompt-based dataset stubs.")
    prompt_parser.add_argument("--prompt-name", required=True, help="Logical prompt or template name.")
    prompt_parser.add_argument("--count", type=int, default=10, help="Number of records to create.")
    prompt_parser.add_argument("--seed-text", help="Optional seed text stored with each record.")
    prompt_parser.add_argument(
        "--output",
        default="prompt_dataset.json",
        help="Output filename under DataSingh/curated.",
    )
    prompt_parser.set_defaults(func=command_prompt)

    hf_parser = subparsers.add_parser("hf", help="Pull a dataset from Hugging Face.")
    hf_parser.add_argument("--dataset-id", required=True, help="Hugging Face dataset id.")
    hf_parser.add_argument("--config-name", help="Optional dataset config name.")
    hf_parser.add_argument("--split", default="train", help="Dataset split to pull.")
    hf_parser.add_argument("--limit", type=int, help="Optional max rows to save.")
    hf_parser.add_argument(
        "--output",
        default="hf_dataset.json",
        help="Output filename under DataSingh/curated.",
    )
    hf_parser.set_defaults(func=command_hf)

    curate_parser = subparsers.add_parser(
        "curate-terms",
        help="Generate term usage examples from local Ollama and mark curated terms.",
    )
    curate_parser.add_argument("--model", default="mistral", help="Local Ollama model name.")
    curate_parser.add_argument(
        "--term-limit",
        type=int,
        help="Optional total number of uncurated terms to process this run.",
    )
    curate_parser.add_argument(
        "--min-examples",
        type=int,
        default=5,
        help="Minimum examples required per term.",
    )
    curate_parser.add_argument(
        "--max-examples",
        type=int,
        default=10,
        help="Maximum examples to keep per term.",
    )
    curate_parser.add_argument(
        "--ollama-host",
        default="http://localhost:11434",
        help="Base URL for the local Ollama server.",
    )
    curate_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=600,
        help="Request timeout for each Ollama batch call.",
    )
    curate_parser.set_defaults(func=command_curate_terms)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
