from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def user_identifier(request: Request) -> str:
    """
    Prefer authenticated user id from request.state.user (set by middleware).
    Fallback to IP address for unauthenticated requests.
    """
    user = getattr(request.state, "user", None)
    if user and user.get("id"):
        return f"user:{user['id']}"
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=user_identifier)
