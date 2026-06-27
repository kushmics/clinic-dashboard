"""Simple bearer-token auth for the prototype API."""
from hmac import compare_digest

from fastapi import Header, HTTPException, status

from app.config import settings


def require_auth(authorization: str | None = Header(default=None)) -> None:
    """Require a bearer token when auth is enabled."""
    if not settings.auth_enabled:
        return

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not compare_digest(token, settings.auth_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid bearer token",
        )
