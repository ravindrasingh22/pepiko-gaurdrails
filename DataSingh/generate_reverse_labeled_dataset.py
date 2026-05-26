from __future__ import annotations

import argparse
import csv
import json
import socket
import sys
from pathlib import Path
from typing import Any
from urllib import error, request


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLASSIFIER_ROOT = PROJECT_ROOT / "classifier"
if str(CLASSIFIER_ROOT) not in sys.path:
    sys.path.insert(0, str(CLASSIFIER_ROOT))

from training.slm_classifier.data_pipeline import FLAG_VOCAB, G1_VOCAB, G2_VOCAB


DEFAULT_INPUT_CSV = PROJECT_ROOT / "DataSingh" / "curated" / "toxicchat0124" / "toxicchat0124_train_user_input_model_output.csv"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "DataSingh" / "curated" / "toxicchat0124"
DEFAULT_MANUAL_PATH = PROJECT_ROOT / "lov_question_generation_manual_v2.md"
DEFAULT_DEBUG_DIR = PROJECT_ROOT / "DataSingh" / "debug"

SOURCE_GENERATED_COL = "reverse_questions_generated"
SOURCE_STATUS_COL = "reverse_questions_status"
SOURCE_COUNT_COL = "reverse_questions_count"
SOURCE_ATTEMPTED_COL = "reverse_questions_attempted"

OUTPUT_COLUMNS = ["user_input", "g1", "g2", "flags"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate reverse labeled user inputs from any source CSV using a local Ollama-compatible model."
    )
    parser.add_argument("--input-csv", default=str(DEFAULT_INPUT_CSV))
    parser.add_argument("--output-csv", default="")
    parser.add_argument("--source-input-column", default="user_input")
    parser.add_argument("--source-output-column", default="model_output")
    parser.add_argument("--manual-path", default=str(DEFAULT_MANUAL_PATH))
    parser.add_argument("--model", default="mistral")
    parser.add_argument("--ollama-host", default="http://localhost:11434")
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--min-rows", type=int, default=8)
    parser.add_argument("--max-rows", type=int, default=16)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-row", type=int, default=0, help="1-based source CSV row number inclusive, counting header as row 1.")
    parser.add_argument("--end-row", type=int, default=0, help="1-based source CSV row number inclusive, counting header as row 1.")
    parser.add_argument("--batch-size", type=int, default=1, help="Number of source rows to send in one Ollama call.")
    parser.add_argument("--temperature", type=float, default=0.9)
    parser.add_argument("--debug-file", default="")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sanitize_model_name(model: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in (model or "").strip())
    return cleaned or "model"


def append_debug_record(debug_path: Path, payload: dict[str, Any]) -> None:
    debug_path.parent.mkdir(parents=True, exist_ok=True)
    with debug_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_text(value: str) -> str:
    return " ".join((value or "").split())


def parse_json_payload(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        candidates: list[str] = []

        def largest_balanced_json_block(value: str) -> str:
            start_index = -1
            depth = 0
            in_string = False
            escape = False
            best = ""
            for index, char in enumerate(value):
                if escape:
                    escape = False
                    continue
                if char == "\\":
                    escape = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == "{":
                    if depth == 0:
                        start_index = index
                    depth += 1
                elif char == "}":
                    if depth > 0:
                        depth -= 1
                        if depth == 0 and start_index != -1:
                            candidate = value[start_index : index + 1]
                            if len(candidate) > len(best):
                                best = candidate
            return best

        balanced = largest_balanced_json_block(text)
        if balanced:
            candidates.append(balanced)

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1])
        fenced_start = text.find("```json")
        if fenced_start != -1:
            fenced_body = text[fenced_start + 7 :]
            fenced_end = fenced_body.find("```")
            if fenced_end != -1:
                candidates.append(fenced_body[:fenced_end].strip())
        fenced_start = text.find("```")
        if fenced_start != -1:
            fenced_body = text[fenced_start + 3 :]
            fenced_end = fenced_body.find("```")
            if fenced_end != -1:
                candidates.append(fenced_body[:fenced_end].strip())
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                repaired = candidate.replace("\r", " ").replace("\n", " ")
                repaired = repaired.replace("'", '"')
                repaired = repaired.replace(",}", "}").replace(",]", "]")
                repaired = repaired.replace("\t", " ")
                try:
                    return json.loads(repaired)
                except json.JSONDecodeError:
                    compact_lines = " ".join(line.strip() for line in candidate.splitlines() if line.strip())
                    compact_lines = compact_lines.replace("'", '"').replace(",}", "}").replace(",]", "]")
                    try:
                        return json.loads(compact_lines)
                    except json.JSONDecodeError:
                        pass
                    continue
        raise


def call_ollama_chat(model: str, prompt: str, host: str, timeout_seconds: int, temperature: float) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": temperature},
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
        raise TimeoutError(f"Ollama request timed out after {timeout_seconds} seconds at {host}.") from exc
    except socket.timeout as exc:
        raise TimeoutError(f"Ollama socket timed out after {timeout_seconds} seconds at {host}.") from exc
    except error.URLError as exc:
        raise ConnectionError(f"Failed to reach Ollama at {host}: {exc}") from exc


def read_source_rows(input_path: Path, source_output_column: str) -> tuple[list[str], list[dict[str, str]]]:
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Input CSV has no headers: {input_path}")
        rows = list(reader)
        fieldnames = list(reader.fieldnames)
    if source_output_column not in fieldnames:
        raise ValueError(f"Missing source output column '{source_output_column}' in {input_path}")
    for required in [SOURCE_GENERATED_COL, SOURCE_STATUS_COL, SOURCE_COUNT_COL, SOURCE_ATTEMPTED_COL]:
        if required not in fieldnames:
            fieldnames.append(required)
    return fieldnames, rows


def write_source_rows(input_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with input_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in fieldnames})


def append_rows(output_path: Path, rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output_path.exists() or output_path.stat().st_size == 0
    with output_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        if write_header:
            writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in OUTPUT_COLUMNS})


def load_existing_rows(output_path: Path) -> set[tuple[str, str, str, str]]:
    if not output_path.exists():
        return set()
    existing: set[tuple[str, str, str, str]] = set()
    with output_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            existing.add(
                (
                    normalize_text(row.get("user_input", "")).lower(),
                    normalize_text(row.get("g1", "")),
                    normalize_text(row.get("g2", "")),
                    normalize_text(row.get("flags", "")),
                )
            )
    return existing


def manual_excerpt(manual_path: Path) -> str:
    text = manual_path.read_text(encoding="utf-8")
    anchors = [
        "## Fixed taxonomy",
        "## Fixed flag set",
        "## Core labeling principle",
        "## How to choose G1",
        "## How to choose G2",
        "## Stable flag rules",
    ]
    chunks: list[str] = []
    for anchor in anchors:
        start = text.find(anchor)
        if start == -1:
            continue
        next_header = text.find("\n## ", start + 4)
        end = next_header if next_header != -1 else len(text)
        chunks.append(text[start:end].strip())
    return "\n\n".join(chunks)


def build_batch_prompt(
    batch_rows: list[dict[str, str]],
    min_rows: int,
    max_rows: int,
    manual_text: str,
    source_input_column: str,
    source_output_column: str,
) -> str:
    batch_payload = [
        {
            "source_row_number": int(row["source_row_number"]),
            "source_input": row["source_input_text"],
            "source_output": row["source_output_text"],
        }
        for row in batch_rows
    ]
    return "\n".join(
        [
            "You are generating a labeled child-safety training dataset.",
            "Use the allowed GL-codebook labels only.",
            f"Allowed G1 values: {', '.join(G1_VOCAB)}",
            f"Allowed G2 values: {', '.join(G2_VOCAB)}",
            f"Allowed flags: {', '.join(FLAG_VOCAB)}",
            "Generate reverse user_input rows that could plausibly lead to the source output.",
            "Return only rows that sound like realistic child or teen inputs, including simple kid phrasing, preteen phrasing, and Gen Z teen wording where appropriate.",
            "Some reverse user_input rows can be questions, short requests, commands, statements, roleplay continuations, jailbreak-like prompts, emotional disclosures, or unsafe asks.",
            "Keep enough context inside each user_input so the source output makes sense as a reply.",
            "Do not make vague rows without context.",
            "Use the original source input as hidden context and style guidance, but do not just paraphrase it repeatedly.",
            "Focus more strongly on risky LOVs when the output supports them. Prefer sharp positives for SELF_HARM, UNSAFE_SEXUAL_CONTENT, GROOMING, COERCIVE_CONTROL, VULN_EXPLOIT, DANGEROUS, VIOLENCE, BULLYING, EMOTIONAL, and AMBIGUOUS_RISK when plausible.",
            "Do not soften, sanitize, or neutralize unsafe rows if the source output could realistically be triggered by unsafe phrasing.",
            "This is training data generation, not a safety response. Preserve unsafe, sexual, manipulative, violent, hateful, or self-harm-seeking wording when it plausibly fits the source output.",
            "Do not refuse because content is unsafe. Instead, label it correctly with g1, g2, and flags.",
            "When the output is harmless or generic, still include realistic boundary and ambiguous variants if they plausibly fit.",
            "If some generated rows do not fit the LOV taxonomy cleanly, still include them.",
            'For those non-fitting rows, keep g1 if possible, and leave g2 as an empty string and flags as an empty JSON object {}.',
            "Try to cover all four row types when possible: clear positives, risky rows, ambiguous rows, and non-fitting boundary rows.",
            "Use the strongest-LOV rule for g2. Do not stuff many g2 values into one row unless necessary.",
            "flags must be a JSON object using only the allowed flags and boolean values.",
            "g2 must be a comma-separated string if more than one label is truly needed, otherwise a single label string.",
            f"For each source row, return between {min_rows} and {max_rows} labeled rows if possible.",
            'Return JSON exactly in this shape: {"items":[{"source_row_number":123,"rows":[{"user_input":"...","g1":"...","g2":"...","flags":{"direct_intent":false}}]}]}',
            "If you want, inside each source row object you may conceptually mix clear positives, risky rows, ambiguous rows, and non-fitting boundary rows, but the final JSON must still use the exact shape above.",
            "",
            "LOV manual guidance:",
            manual_text,
            "",
            f"Batch source rows with {source_input_column} and {source_output_column}:",
            json.dumps(batch_payload, ensure_ascii=True),
        ]
    )


def normalize_g2_value(raw: object) -> str:
    if isinstance(raw, list):
        values = [str(item).strip() for item in raw if str(item).strip()]
    else:
        values = [item.strip() for item in str(raw or "").split(",") if item.strip()]
    deduped: list[str] = []
    for value in values:
        if value in G2_VOCAB and value not in deduped:
            deduped.append(value)
    return ",".join(deduped)


def normalize_flags(raw: object) -> str:
    result = {flag: False for flag in FLAG_VOCAB}
    if isinstance(raw, dict):
        for key, value in raw.items():
            key_str = str(key).strip()
            if key_str in result:
                result[key_str] = bool(value)
    return json.dumps(result, sort_keys=True)


def classify_fallback(user_input: str) -> tuple[str, str, str]:
    text = normalize_text(user_input).lower()
    flags = {flag: False for flag in FLAG_VOCAB}

    def has_any(terms: list[str]) -> bool:
        return any(term in text for term in terms)

    self_harm_terms = ["kill myself", "hurt myself", "suicide", "suicidal", "want to die", "shouldn't be here", "shouldnt be here", "cut myself", "disappear forever", "end my life"]
    sexual_terms = ["porn", "nudes", "naked", "sex", "sexual", "fetish", "vibrator", "explicit pictures"]
    grooming_terms = ["keep it secret", "dont tell anyone", "don't tell anyone", "older person", "older guy", "sent me gifts", "wants to meet alone", "special friend online"]
    coercive_terms = ["controls everything", "control everything", "i get hurt if", "not allowed to", "tracks my phone", "checks my messages", "forces me", "won't let me", "wont let me"]
    vuln_terms = ["blackmail", "knows my secret", "uses my secret", "only they understand me", "if i dont do it theyll tell", "if i don't do it they'll tell"]
    hate_terms = ["all muslims", "all jews", "all gays", "all black people", "all white people", "slur", "disgusting", "inferior", "get rid of"]
    dangerous_terms = ["make a bomb", "make drugs", "hack", "break in", "avoid getting caught", "poison"]
    violence_terms = ["hurt someone", "kill him", "kill her", "stab", "weapon", "beat him", "beat her", "attack"]
    bullying_terms = ["kids are mean", "call me names", "left out", "exclude me", "bullied", "picked on"]
    emotional_terms = ["worthless", "hopeless", "sad", "alone", "lonely", "cry", "scared", "afraid", "depressed", "anxious", "overwhelmed", "empty", "numb"]
    personal_direction_terms = ["what should i do", "should i", "what do i do", "how should i", "do i tell", "is it okay if i"]
    safety_terms = ["is it safe", "unsafe", "hazard", "electric shock", "fire", "mix chemicals", "overdose"]
    ambiguous_terms = ["is this normal", "not sure if", "feels weird", "kind of scared", "maybe this is bad"]
    tech_terms = ["online", "discord", "snapchat", "instagram", "tiktok", "dm", "text", "phone", "chat", "app"]
    death_terms = ["died", "passed away", "funeral", "grief", "lost my"]

    if has_any(self_harm_terms):
        g2 = "SELF_HARM"
        flags["has_self_harm"] = True
        flags["has_emotional_distress"] = True
        if has_any(["i want to", "how do i", "best way to", "i'm going to", "im going to"]):
            flags["direct_intent"] = True
        else:
            flags["indirect_intent"] = True
    elif has_any(grooming_terms):
        g2 = "GROOMING"
        flags["has_grooming_involved"] = True
        flags["has_vuln_exploit"] = True
    elif has_any(vuln_terms):
        g2 = "VULN_EXPLOIT"
        flags["has_vuln_exploit"] = True
    elif has_any(coercive_terms):
        g2 = "COERCIVE_CONTROL"
        flags["has_coercive_control"] = True
        flags["has_emotional_distress"] = True
    elif has_any(sexual_terms):
        g2 = "UNSAFE_SEXUAL_CONTENT"
        flags["has_unsafe_sexual_content"] = True
    elif has_any(hate_terms):
        g2 = "HATE_GROUP"
        flags["has_hate_group_language"] = True
    elif has_any(dangerous_terms):
        g2 = "DANGEROUS"
        flags["has_dangerous_context"] = True
    elif has_any(violence_terms):
        g2 = "VIOLENCE"
        flags["has_violence_possibility"] = True
    elif has_any(safety_terms):
        g2 = "SAFETY_HAZARD"
        flags["has_safety_hazard"] = True
    elif has_any(bullying_terms):
        g2 = "BULLYING"
        flags["has_bullying_involved"] = True
    elif has_any(personal_direction_terms):
        g2 = "PERSONAL_DIRECTION"
        flags["has_personal_direction"] = True
        flags["direct_intent"] = True
        if has_any(emotional_terms):
            flags["has_emotional_distress"] = True
    elif has_any(emotional_terms):
        g2 = "EMOTIONAL"
        flags["has_emotional_distress"] = True
    elif has_any(ambiguous_terms):
        g2 = "AMBIGUOUS_RISK"
        flags["has_ambiguous_risk"] = True
        flags["needs_clarification"] = True
    else:
        g2 = ""

    if has_any(tech_terms):
        g1 = "TECHNOLOGY"
    elif has_any(death_terms):
        g1 = "DEATH_GRIEF"
    else:
        g1 = "GENERIC"
    if not g2:
        return g1, "", "{}"
    return g1, g2, json.dumps(flags, sort_keys=True)


def normalize_generated_rows(
    response_payload: dict[str, Any],
    max_rows: int,
    existing_rows: set[tuple[str, str, str, str]],
    expected_source_row_numbers: list[int],
) -> dict[int, list[dict[str, str]]]:
    content = response_payload.get("message", {}).get("content", "")
    parsed = parse_json_payload(content)
    items = parsed.get("items", [])
    grouped_rows: dict[int, list[dict[str, str]]] = {}
    flat_fallback_items: list[Any] = []

    def normalize_single_item(item: Any) -> dict[str, str] | None:
        if isinstance(item, dict):
            user_input = normalize_text(
                str(item.get("user_input", "") or item.get("question", "") or item.get("input", "") or item.get("text", ""))
            )
            g1 = normalize_text(str(item.get("g1", "")))
            g2 = normalize_g2_value(item.get("g2", ""))
            flags = normalize_flags(item.get("flags", {}))
        else:
            user_input = normalize_text(str(item))
            g1 = ""
            g2 = ""
            flags = ""
        if not user_input or len(user_input) < 8:
            return None
        if g1 not in G1_VOCAB or not g2:
            fallback_g1, fallback_g2, fallback_flags = classify_fallback(user_input)
            if g1 not in G1_VOCAB:
                g1 = fallback_g1
            if not g2 and fallback_g2:
                g2 = fallback_g2
            if not flags and fallback_flags != "{}":
                flags = fallback_flags
        if g1 not in G1_VOCAB:
            return None
        if g2 and not flags:
            _, _, flags = classify_fallback(user_input)
        if not g2:
            flags = "{}"
        row_key = (user_input.lower(), g1, g2, flags)
        if row_key in existing_rows:
            return None
        existing_rows.add(row_key)
        return {"user_input": user_input, "g1": g1, "g2": g2, "flags": flags}

    if not items:
        list_like_keys = [
            "positive_items",
            "negative_items",
            "clear_positive",
            "clear_positives",
            "risky",
            "risky_rows",
            "ambiguous",
            "ambiguous_rows",
            "non_fitting_boundary",
            "non_fitting_boundary_rows",
            "boundary",
            "boundary_rows",
            "non_fitting",
            "other",
        ]
        for key in list_like_keys:
            value = parsed.get(key, [])
            if isinstance(value, list):
                flat_fallback_items.extend(value)

    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            flat_fallback_items.append(item)
            continue
        try:
            source_row_number = int(item.get("source_row_number", 0))
        except (TypeError, ValueError):
            flat_fallback_items.append(item)
            continue
        raw_rows = item.get("rows", [])
        if not isinstance(raw_rows, list):
            flat_fallback_items.append(item)
            continue
        normalized_bucket: list[dict[str, str]] = []
        for raw_row in raw_rows:
            normalized = normalize_single_item(raw_row)
            if normalized is None:
                continue
            normalized_bucket.append(normalized)
            if len(normalized_bucket) >= max_rows:
                break
        grouped_rows[source_row_number] = normalized_bucket

    # If the model ignored per-row grouping, salvage flat items and spread them across the batch.
    if not any(grouped_rows.get(row_number) for row_number in expected_source_row_numbers) and flat_fallback_items:
        normalized_flat: list[dict[str, str]] = []
        for raw_item in flat_fallback_items:
            normalized = normalize_single_item(raw_item)
            if normalized is None:
                continue
            normalized_flat.append(normalized)
        if normalized_flat:
            for row_number in expected_source_row_numbers:
                grouped_rows.setdefault(row_number, [])
            for index, normalized in enumerate(normalized_flat):
                row_number = expected_source_row_numbers[index % len(expected_source_row_numbers)]
                if len(grouped_rows[row_number]) < max_rows:
                    grouped_rows[row_number].append(normalized)

    return grouped_rows


def mark_source_row(row: dict[str, str], generated: str, status: str, count: int = 0, attempted: str = "yes") -> None:
    row[SOURCE_GENERATED_COL] = generated
    row[SOURCE_STATUS_COL] = status
    row[SOURCE_COUNT_COL] = str(count)
    row[SOURCE_ATTEMPTED_COL] = attempted


def main() -> None:
    args = parse_args()
    if args.min_rows < 1:
        raise SystemExit("--min-rows must be at least 1.")
    if args.max_rows < args.min_rows:
        raise SystemExit("--max-rows cannot be smaller than --min-rows.")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be at least 1.")

    input_path = Path(args.input_csv)
    output_path = (
        Path(args.output_csv)
        if args.output_csv
        else DEFAULT_OUTPUT_DIR / f"{sanitize_model_name(args.model)}_reverse_part_1.csv"
    )
    debug_path = (
        Path(args.debug_file)
        if args.debug_file
        else DEFAULT_DEBUG_DIR / f"{sanitize_model_name(args.model)}_failed_batches.jsonl"
    )
    manual_text = manual_excerpt(Path(args.manual_path))
    source_fieldnames, source_rows = read_source_rows(input_path, args.source_output_column)
    existing_rows = load_existing_rows(output_path)
    if source_rows and args.source_input_column not in source_rows[0]:
        raise ValueError(f"Missing source input column '{args.source_input_column}' in {input_path}")

    pending_indexes = [
        index for index, row in enumerate(source_rows)
        if args.force or (
            normalize_text(row.get(SOURCE_GENERATED_COL, "")).lower() not in {"yes", "generated", "true", "1"}
            and normalize_text(row.get(SOURCE_ATTEMPTED_COL, "")).lower() not in {"yes", "true", "1"}
        )
    ]
    if args.start_row > 0:
        pending_indexes = [index for index in pending_indexes if index + 2 >= args.start_row]
    if args.end_row > 0:
        pending_indexes = [index for index in pending_indexes if index + 2 <= args.end_row]
    if args.limit > 0:
        pending_indexes = pending_indexes[:args.limit]

    written_count = 0
    failed_count = 0
    skipped_count = 0

    total_batches = (len(pending_indexes) + args.batch_size - 1) // args.batch_size if pending_indexes else 0
    for batch_index in range(0, len(pending_indexes), args.batch_size):
        batch_source_indexes = pending_indexes[batch_index:batch_index + args.batch_size]
        batch_rows: list[dict[str, str]] = []
        batch_label = (batch_index // args.batch_size) + 1
        for source_index in batch_source_indexes:
            row = source_rows[source_index]
            row_number = source_index + 2
            source_input_text = normalize_text(row.get(args.source_input_column, ""))
            source_output_text = normalize_text(row.get(args.source_output_column, ""))
            if not source_output_text:
                print(f"[reverse-questions] skip row={row_number} reason=empty_source_output")
                mark_source_row(row, generated="yes", status="skipped_empty", count=0)
                skipped_count += 1
                continue
            batch_rows.append(
                {
                    "source_index": str(source_index),
                    "source_row_number": str(row_number),
                    "source_input_text": source_input_text,
                    "source_output_text": source_output_text,
                }
            )
            mark_source_row(row, generated="no", status="started", count=0, attempted="yes")
        write_source_rows(input_path, source_fieldnames, source_rows)
        if not batch_rows:
            continue
        prompt = build_batch_prompt(
            batch_rows=batch_rows,
            min_rows=args.min_rows,
            max_rows=args.max_rows,
            manual_text=manual_text,
            source_input_column=args.source_input_column,
            source_output_column=args.source_output_column,
        )
        batch_row_numbers = ",".join(item["source_row_number"] for item in batch_rows)
        print(f"[reverse-questions] batch={batch_label}/{total_batches} source_rows={batch_row_numbers} calling model={args.model}")
        response_payload: dict[str, Any] | None = None
        try:
            response_payload = call_ollama_chat(
                model=args.model,
                prompt=prompt,
                host=args.ollama_host,
                timeout_seconds=args.timeout_seconds,
                temperature=args.temperature,
            )
            generated_rows_by_source = normalize_generated_rows(
                response_payload=response_payload,
                max_rows=args.max_rows,
                existing_rows=existing_rows,
                expected_source_row_numbers=[int(item["source_row_number"]) for item in batch_rows],
            )
        except TimeoutError as exc:
            print(f"[reverse-questions] timeout batch={batch_label} source_rows={batch_row_numbers} error={exc}")
            append_debug_record(
                debug_path,
                {
                    "batch": batch_label,
                    "source_rows": [int(item["source_row_number"]) for item in batch_rows],
                    "error_type": "timeout",
                    "error": str(exc),
                    "model": args.model,
                    "prompt": prompt,
                    "response_payload": response_payload,
                },
            )
            for item in batch_rows:
                row = source_rows[int(item["source_index"])]
                mark_source_row(row, generated="yes", status="timeout_generated", count=0, attempted="yes")
            write_source_rows(input_path, source_fieldnames, source_rows)
            failed_count += len(batch_rows)
            continue
        except Exception as exc:
            print(f"[reverse-questions] failed batch={batch_label} source_rows={batch_row_numbers} error={exc}")
            append_debug_record(
                debug_path,
                {
                    "batch": batch_label,
                    "source_rows": [int(item["source_row_number"]) for item in batch_rows],
                    "error_type": exc.__class__.__name__,
                    "error": str(exc),
                    "model": args.model,
                    "prompt": prompt,
                    "response_payload": response_payload,
                },
            )
            for item in batch_rows:
                row = source_rows[int(item["source_index"])]
                mark_source_row(row, generated="yes", status="failed_generated", count=0, attempted="yes")
            write_source_rows(input_path, source_fieldnames, source_rows)
            failed_count += len(batch_rows)
            continue
        rows_to_append: list[dict[str, str]] = []
        for item in batch_rows:
            source_index = int(item["source_index"])
            row_number = int(item["source_row_number"])
            row = source_rows[source_index]
            generated_rows = generated_rows_by_source.get(row_number, [])
            if not generated_rows:
                print(f"[reverse-questions] source_row={row_number} produced zero usable rows")
                mark_source_row(row, generated="yes", status="no_usable_rows", count=0, attempted="yes")
                skipped_count += 1
                continue
            rows_to_append.extend(generated_rows)
            row_status = "generated" if len(generated_rows) >= args.min_rows else "partial_generated"
            mark_source_row(row, generated="yes", status=row_status, count=len(generated_rows), attempted="yes")
            written_count += len(generated_rows)
            print(f"[reverse-questions] source_row={row_number} wrote={len(generated_rows)} status={row_status}")
            for item_index, generated_row in enumerate(generated_rows, start=1):
                print(
                    f"[reverse-questions] source_row={row_number} item_{item_index}: "
                    f"user_input={generated_row['user_input']} | g1={generated_row['g1']} | "
                    f"g2={generated_row['g2']} | flags={generated_row['flags']}"
                )
        if rows_to_append:
            append_rows(output_path, rows_to_append)
        write_source_rows(input_path, source_fieldnames, source_rows)

    print(f"[reverse-questions] done output={output_path}")
    print(f"[reverse-questions] written_rows={written_count}")
    print(f"[reverse-questions] skipped_rows={skipped_count}")
    print(f"[reverse-questions] failed_rows={failed_count}")


if __name__ == "__main__":
    main()
