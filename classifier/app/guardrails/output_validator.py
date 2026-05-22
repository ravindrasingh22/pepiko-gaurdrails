from typing import Any


def validate(child_profile: Any, user_message: str, answer: str, policy_decision: Any) -> dict[str, Any]:
    unsafe = any(term in answer.lower() for term in ["secret", "hide it", "don't tell"])
    return {
        "safe_to_show": not unsafe,
        "violations": ["secrecy"] if unsafe else [],
    }
