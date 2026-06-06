from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

DEFAULT_CHAT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def _device_map() -> str | None:
    if torch.cuda.is_available():
        return "auto"
    return None


@lru_cache(maxsize=1)
def load_chat_model(model_name: str | None = None) -> tuple[Any, Any, str]:
    model_name = (model_name or os.environ.get("CHAT_MODEL_SLUG", DEFAULT_CHAT_MODEL)).strip() or DEFAULT_CHAT_MODEL
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model_kwargs: dict[str, Any] = {"torch_dtype": "auto"}
    device_map = _device_map()
    if device_map is not None:
        model_kwargs["device_map"] = device_map
    model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
    return tokenizer, model, model_name


def warm_chat_model() -> dict[str, str]:
    _, _, model_name = load_chat_model()
    return {"model_name": model_name, "status": "loaded"}


def generate_chat_response(
    *,
    messages: list[dict[str, str]],
    max_new_tokens: int = 256,
    temperature: float = 0.2,
    model_name: str | None = None,
) -> dict[str, Any]:
    tokenizer, model, resolved_model_name = load_chat_model(model_name)
    text = tokenizer.apply_chat_template(
        messages,
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
        "model_name": resolved_model_name,
        "answer": answer,
        "messages": messages,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }
