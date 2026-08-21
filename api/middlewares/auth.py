# -*- coding: utf-8 -*-
"""
Auth middleware: protect /api/v1/* when admin auth is enabled.
"""

from __future__ import annotations

import logging
from typing import Callable

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.auth import COOKIE_NAME, has_stored_password, is_auth_enabled, verify_session
from src.network_bind_security import is_request_from_non_loopback_bind

logger = logging.getLogger(__name__)

EXEMPT_PATHS = frozenset({
    "/api/v1/auth/login",
    "/api/v1/auth/status",
    "/api/health",
    "/api/v1/health",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
})


def _path_exempt(path: str) -> bool:
    """Check if path is exempt from auth."""
    normalized = path.rstrip("/") or "/"
    return normalized in EXEMPT_PATHS


class AuthMiddleware(BaseHTTPMiddleware):
    """Require valid session for /api/v1/* when auth is enabled."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable,
    ):
        auth_enabled = is_auth_enabled()
        if is_request_from_non_loopback_bind(request):
            if not auth_enabled:
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "public_bind_auth_required",
                        "message": (
                            "Public API access is unavailable while "
                            "ADMIN_AUTH_ENABLED=false"
                        ),
                    },
                )
            if not has_stored_password():
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "public_bind_password_required",
                        "message": (
                            "Public API access requires an existing admin password; "
                            "complete setup on loopback first"
                        ),
                    },
                )

        if not auth_enabled:
            return await call_next(request)

        path = request.url.path
        if _path_exempt(path):
            return await call_next(request)

        if not path.startswith("/api/v1/"):
            return await call_next(request)

        cookie_val = request.cookies.get(COOKIE_NAME)
        if not cookie_val or not verify_session(cookie_val):
            return JSONResponse(
                status_code=401,
                content={
                    "error": "unauthorized",
                    "message": "Login required",
                },
            )

        return await call_next(request)


def add_auth_middleware(app):
    """Add auth middleware to protect API routes.

    The middleware is always registered; whether auth is enforced is determined
    at request time by is_auth_enabled() so the decision stays consistent across
    any runtime configuration reload.
    """
    app.add_middleware(AuthMiddleware)
