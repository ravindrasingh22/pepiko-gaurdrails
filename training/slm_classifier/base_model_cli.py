from __future__ import annotations

import argparse

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
except Exception:  # pragma: no cover
    torch = None
    AutoModelForCausalLM = None
    AutoTokenizer = None


MODEL_NAME = "HuggingFaceTB/SmolLM2-135M"


def _device() -> str:
    if torch is None:
        raise RuntimeError("Torch is not available.")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _build_prompt(question: str, age_band: str, language: str) -> str:
    return (
        f"You are answering a child in age band {age_band}. "
        f"Respond in language: {language}. "
        f"Question: {question}\n"
        "Answer:"
    )


def _run_base_model(
    question: str,
    age_band: str,
    language: str,
    max_new_tokens: int = 120,
) -> dict[str, str]:
    if not (torch and AutoModelForCausalLM and AutoTokenizer):
        raise RuntimeError("Transformers/Torch dependencies are not available.")
    device = _device()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME).to(device)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    prompt = _build_prompt(question, age_band, language)
    inputs = tokenizer(prompt, return_tensors="pt").to(device)
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
        )
    return {
        "model_name": MODEL_NAME,
        "device": device,
        "prompt": prompt,
        "text": tokenizer.decode(output[0], skip_special_tokens=True),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the raw base HuggingFace SmolLM2 model directly.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--age-band", default="11-12")
    parser.add_argument("--language", default="en")
    parser.add_argument("--max-new-tokens", type=int, default=120)
    args = parser.parse_args()

    result = _run_base_model(
        question=args.question,
        age_band=args.age_band,
        language=args.language,
        max_new_tokens=args.max_new_tokens,
    )
    print(f"model_name: {result['model_name']}")
    print(f"device: {result['device']}")
    print("prompt:")
    print(result["prompt"])
    print("output:")
    print(result["text"])


if __name__ == "__main__":
    main()
