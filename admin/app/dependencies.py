from app.security import decode_token
from fastapi import HTTPException, Request, status
from fastapi.responses import RedirectResponse


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
        return decode_token(token)
    return None


async def verify_token(request: Request) -> str | RedirectResponse:
    """
    Verify user token and handle expired sessions.

    This function handles expired or unauthenticated sessions differently
    for HTML pages vs API requests:

    - HTML requests: redirect to /login
    - API requests: raise 401 Unauthorized

    Returns:
        str | RedirectResponse: Username if authenticated,
        or RedirectResponse to /login for HTML requests.

    Raises:
        HTTPException: If the user is not authenticated.
    """
    user = await get_current_user_optional(request)
    if user:
        return user

    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse("/login")
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


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
