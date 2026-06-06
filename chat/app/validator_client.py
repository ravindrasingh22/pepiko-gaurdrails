from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Literal


DEFAULT_VALIDATOR_URL = "http://localhost:4003/api/v1/guardrail/validate"
VALIDATOR_URL = os.environ.get("CHAT_VALIDATOR_URL", DEFAULT_VALIDATOR_URL)


def validate_assistant_response(*, content: str, child_profile: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "message": {
            "role": "assistant",
            "content": content,
        },
        "child_profile": child_profile,
    }
    request = urllib.request.Request(
        VALIDATOR_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        return _fail_closed_validation(str(exc))

    return {
        "response_validation": _validation_label(raw.get("response_validation")),
        "validation_score": float(raw.get("validation_score", 0.0)),
        "validator_usage": _validator_usage(raw.get("validator_usage")),
    }


def _validation_label(value: object) -> Literal["Safe", "UnSafe"]:
    return "Safe" if str(value) == "Safe" else "UnSafe"


def _validator_usage(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    prompt_tokens = int(value.get("prompt_tokens", 0))
    completion_tokens = int(value.get("completion_tokens", 0))
    total_tokens = int(value.get("total_tokens", prompt_tokens + completion_tokens))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _fail_closed_validation(error: str) -> dict[str, Any]:
    return {
        "response_validation": "UnSafe",
        "validation_score": 1.0,
        "validator_usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "validator_error": error,
    }
