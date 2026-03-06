"""Optional HTTP Basic authentication middleware."""

from __future__ import annotations

import secrets
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config import settings

security = HTTPBasic(auto_error=False)


async def check_auth(credentials: HTTPBasicCredentials | None = Depends(security)):
    """If --user/--password were provided at startup, enforce HTTP Basic auth."""
    if settings.username is None and settings.password is None:
        # Auth disabled
        return

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    correct_user = secrets.compare_digest(credentials.username, settings.username or "")
    correct_pass = secrets.compare_digest(credentials.password, settings.password or "")

    if not (correct_user and correct_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
