from __future__ import annotations

import argparse

try:
    import torch
    from transformers import AutoModel, AutoTokenizer
except Exception:  # pragma: no cover
    torch = None
    AutoModel = None
    AutoTokenizer = None


MODEL_NAME = "microsoft/deberta-v3-xsmall"


def _device() -> str:
    if torch is None:
        raise RuntimeError("Torch is not available.")
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _build_text(question: str, age_band: str, language: str) -> str:
    return (
        f"Age band: {age_band}\n"
        f"Language: {language}\n"
        f"Question: {question}"
    )


def _run_encoder(
    question: str,
    age_band: str,
    language: str,
    max_length: int = 128,
) -> dict[str, object]:
    if not (torch and AutoModel and AutoTokenizer):
        raise RuntimeError("Transformers/Torch dependencies are not available.")
    device = _device()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME).to(device)
    text = _build_text(question, age_band, language)
    inputs = tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
    ).to(device)
    with torch.no_grad():
        outputs = model(**inputs)
    cls_like = outputs.last_hidden_state[0, 0, :8].detach().cpu().tolist()
    return {
        "model_name": MODEL_NAME,
        "device": device,
        "text": text,
        "shape": tuple(outputs.last_hidden_state.shape),
        "embedding_sample": cls_like,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the raw DeBERTa v3 xsmall encoder directly.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--age-band", default="11-12")
    parser.add_argument("--language", default="en")
    parser.add_argument("--max-length", type=int, default=128)
    args = parser.parse_args()

    result = _run_encoder(
        question=args.question,
        age_band=args.age_band,
        language=args.language,
        max_length=args.max_length,
    )
    print(f"model_name: {result['model_name']}")
    print(f"device: {result['device']}")
    print("input:")
    print(result["text"])
    print(f"last_hidden_state shape: {result['shape']}")
    print(f"embedding_sample: {result['embedding_sample']}")


if __name__ == "__main__":
    main()
