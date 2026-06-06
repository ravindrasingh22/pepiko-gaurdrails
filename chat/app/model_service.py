from __future__ import annotations

import os
import json
from functools import lru_cache
from typing import Any
from urllib import request

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

LOCAL_CHAT_MODEL = "gemma:2b-instruct"
LOCAL_TRANSFORMERS_CHAT_MODEL = "google/gemma-2-2b-it"
PRODUCTION_CHAT_MODEL = "google/gemma-4-12B"
DEFAULT_CHAT_MODEL = LOCAL_CHAT_MODEL
DEFAULT_CHAT_BACKEND = "ollama"
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
SUPPORTED_CHAT_MODELS = (
    DEFAULT_CHAT_MODEL,
    LOCAL_TRANSFORMERS_CHAT_MODEL,
    "google/gemma-2-9b-it",
    PRODUCTION_CHAT_MODEL,
)
CHAT_MODEL_LICENSES = {
    PRODUCTION_CHAT_MODEL: "Apache 2.0",
}


def _model_family(model_name: str) -> str:
    lowered = model_name.lower()
    if "gemma" in lowered:
        return "gemma"
    return "default"


def _chat_backend(model_name: str | None = None) -> str:
    configured = os.environ.get("CHAT_BACKEND", "").strip().lower()
    if configured:
        return configured
    if model_name and "/" in model_name:
        return "transformers"
    return DEFAULT_CHAT_BACKEND


def _chat_env() -> str:
    return os.environ.get("CHAT_ENV", "local").strip().lower() or "local"


def _resolve_model_name(model_name: str | None = None) -> str:
    resolved = (model_name or os.environ.get("CHAT_MODEL_SLUG", DEFAULT_CHAT_MODEL)).strip() or DEFAULT_CHAT_MODEL
    if resolved == PRODUCTION_CHAT_MODEL and _chat_env() != "production":
        raise ValueError(
            f"{PRODUCTION_CHAT_MODEL} is production-only. "
            "Set CHAT_ENV=production to allow it, or use google/gemma-2-2b-it locally."
        )
    return resolved


def _resolve_ollama_model_name(model_name: str | None = None) -> str:
    return (model_name or os.environ.get("OLLAMA_CHAT_MODEL", LOCAL_CHAT_MODEL)).strip() or LOCAL_CHAT_MODEL


def _device_map() -> str | None:
    if torch.cuda.is_available():
        return "auto"
    return None


@lru_cache(maxsize=1)
def load_chat_model(model_name: str | None = None) -> tuple[Any, Any, str]:
    model_name = _resolve_model_name(model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model_kwargs: dict[str, Any] = {"torch_dtype": "auto"}
    device_map = _device_map()
    if device_map is not None:
        model_kwargs["device_map"] = device_map
    model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
    return tokenizer, model, model_name


def warm_chat_model() -> dict[str, str]:
    if _chat_backend() == "ollama":
        return {"backend": "ollama", "model_name": _resolve_ollama_model_name(), "status": "lazy"}
    _, _, model_name = load_chat_model()
    return {"backend": "transformers", "model_name": model_name, "status": "loaded"}


def _normalize_message(item: dict[str, str]) -> dict[str, str]:
    return {
        "role": str(item.get("role", "")).strip(),
        "content": str(item.get("content", "")).strip(),
    }


def _messages_for_chat_template(messages: list[dict[str, str]], model_name: str) -> list[dict[str, str]]:
    normalized = [_normalize_message(item) for item in messages]
    normalized = [item for item in normalized if item["role"] and item["content"]]
    if _model_family(model_name) != "gemma":
        return normalized

    system_text = "\n\n".join(item["content"] for item in normalized if item["role"] == "system")
    non_system = [item for item in normalized if item["role"] != "system"]
    if not system_text:
        return non_system
    if not non_system:
        return [{"role": "user", "content": system_text}]
    first = dict(non_system[0])
    first["content"] = f"{system_text}\n\nUser request:\n{first['content']}"
    return [first, *non_system[1:]]


def _ollama_chat(
    *,
    messages: list[dict[str, str]],
    max_new_tokens: int,
    temperature: float,
    model_name: str | None,
) -> dict[str, Any]:
    resolved_model_name = _resolve_ollama_model_name(model_name)
    payload = {
        "model": resolved_model_name,
        "messages": [_normalize_message(item) for item in messages],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_new_tokens,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=120) as response:
        raw = json.loads(response.read().decode("utf-8"))
    answer = str(raw.get("message", {}).get("content", "")).strip()
    prompt_tokens = int(raw.get("prompt_eval_count", 0) or 0)
    completion_tokens = int(raw.get("eval_count", 0) or 0)
    return {
        "backend": "ollama",
        "model_name": resolved_model_name,
        "answer": answer,
        "messages": messages,
        "template_messages": payload["messages"],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def generate_chat_response(
    *,
    messages: list[dict[str, str]],
    max_new_tokens: int = 256,
    temperature: float = 0.2,
    model_name: str | None = None,
) -> dict[str, Any]:
    backend = _chat_backend(model_name)
    if backend == "ollama":
        return _ollama_chat(
            messages=messages,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            model_name=model_name,
        )
    if backend != "transformers":
        raise ValueError(f"Unsupported CHAT_BACKEND: {backend}")
    tokenizer, model, resolved_model_name = load_chat_model(model_name)
    template_messages = _messages_for_chat_template(messages, resolved_model_name)
    text = tokenizer.apply_chat_template(
        template_messages,
        tokenize=False,
        add_generation_prompt=True,
    )
    model_inputs = tokenizer([text], return_tensors="pt")
    model_inputs = {key: value.to(model.device) for key, value in model_inputs.items()}
    prompt_tokens = int(model_inputs["input_ids"].shape[-1])
    generated_ids = model.generate(
        **model_inputs,
        max_new_tokens=max_new_tokens,
        do_sample=temperature > 0.0,
        temperature=temperature,
        pad_token_id=tokenizer.eos_token_id,
    )
    completion_ids = generated_ids[:, model_inputs["input_ids"].shape[-1]:]
    answer = tokenizer.batch_decode(completion_ids, skip_special_tokens=True)[0].strip()
    completion_tokens = int(completion_ids.shape[-1])
    return {
        "backend": "transformers",
        "model_name": resolved_model_name,
        "answer": answer,
        "messages": messages,
        "template_messages": template_messages,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
