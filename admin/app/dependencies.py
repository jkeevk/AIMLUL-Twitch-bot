from app.security import decode_token
from fastapi import HTTPException, Request, status


async def get_current_user_optional(request: Request) -> str | None:
    """
    Retrieve current user from JWT cookie if it exists.

    Args:
        request (Request): FastAPI request object.

    Returns:
        str | None: Username if authenticated, None otherwise.
    """
    token = request.cookies.get("session")
    if token:
        try:
            return await decode_token(token)
        except Exception:
            return None
    return None


async def verify_token(request: Request) -> str:
    """
    FastAPI dependency to verify that the user is authenticated.

    Args:
        request (Request): FastAPI request object.

    Returns:
        str: Username.

    Raises:
        HTTPException: If the user is not authenticated.
    """
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def get_client_ip(request: Request) -> str:
    """
    Extract the client's IP address from the request.

    Args:
        request (Request): FastAPI request object.

    Returns:
        str: Client IP address.
    """
    if "x-forwarded-for" in request.headers:
        return str(request.headers["x-forwarded-for"].split(",")[0].strip())

    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"
