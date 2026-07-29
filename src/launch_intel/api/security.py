"""API-key authentication for the read/insights API.

The CRM backend sends a shared secret as the `X-API-Key` header; we compare it
(constant-time) against settings.api_key. If no key is configured the check is
skipped — a local-dev convenience — so production MUST set API_KEY.
"""

import secrets

from fastapi import Header, HTTPException, status

from config.settings import settings

_API_KEY_HEADER = "X-API-Key"


def require_api_key(x_api_key: str | None = Header(default=None, alias=_API_KEY_HEADER)) -> None:
    expected = settings.api_key
    if not expected:
        return  # auth disabled (no key configured) — dev only
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": _API_KEY_HEADER},
        )
