from typing import Any

from app.models.child_profile import ChildProfile


async def build(
    child_profile: ChildProfile,
    message: str,
    session_id: str,
    recent_context: list[str],
) -> dict[str, Any]:
    return {
        "child_profile": child_profile.model_dump(),
        "message": message,
        "session_id": session_id,
        "recent_context": recent_context[-5:],
    }
