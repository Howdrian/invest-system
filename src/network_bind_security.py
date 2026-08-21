# -*- coding: utf-8 -*-
"""Security policy for exposing the Web/API service beyond loopback."""

from __future__ import annotations

import ipaddress
from types import SimpleNamespace
from typing import Any, Optional


APP_BIND_HOST_STATE_KEY = "dsa_bind_host"


def _normalize_host(host: Any) -> str:
    value = "" if host is None else str(host).strip().lower()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if "%" in value:
        value = value.split("%", 1)[0]
    return value.rstrip(".")


def is_loopback_host(host: Any, *, allow_test_sentinel: bool = False) -> bool:
    """Return whether a bind/server host is an explicit loopback address."""
    normalized = _normalize_host(host)
    if normalized == "localhost":
        return True
    if allow_test_sentinel and normalized == "testserver":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def require_safe_network_bind(host: Any) -> None:
    """Reject non-loopback binds unless auth is enabled and already initialized."""
    if is_loopback_host(host):
        return

    # Keep this import lazy so CLI-only workflows do not initialize auth state.
    from src.auth import has_stored_password, is_auth_enabled

    if not is_auth_enabled():
        raise RuntimeError(
            "Refusing a non-loopback API bind while ADMIN_AUTH_ENABLED=false. "
            "Enable admin auth and set an admin password, or keep WEBUI_HOST=127.0.0.1."
        )
    if not has_stored_password():
        raise RuntimeError(
            "Refusing a non-loopback API bind without a stored admin password. "
            "Complete password setup on loopback before exposing the service."
        )


def configure_app_bind_host(app: Any, host: Any) -> None:
    """Record the intended listener host for request-time fail-closed checks."""
    state = getattr(app, "state", None)
    if state is None:
        state = SimpleNamespace()
        setattr(app, "state", state)
    setattr(state, APP_BIND_HOST_STATE_KEY, _normalize_host(host))


def _get_app_bind_host(request: Any) -> Optional[str]:
    scope = getattr(request, "scope", None)
    app = scope.get("app") if isinstance(scope, dict) else None
    if app is None:
        try:
            app = request.app
        except (AttributeError, KeyError, RuntimeError):
            return None

    state = getattr(app, "state", None)
    value = getattr(state, APP_BIND_HOST_STATE_KEY, None) if state is not None else None
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _get_scope_server_host(request: Any) -> Optional[str]:
    scope = getattr(request, "scope", None)
    if not isinstance(scope, dict):
        return None
    server = scope.get("server")
    if not isinstance(server, (tuple, list)) or not server:
        return None
    host = server[0]
    if not isinstance(host, str) or not host.strip():
        return None
    return host


def is_request_from_non_loopback_bind(request: Any) -> bool:
    """Return True when app intent or the ASGI server scope is non-loopback.

    ``testserver`` is Starlette's local TestClient sentinel and is intentionally
    treated as loopback. Unknown/missing scope data is not promoted to public;
    official entrypoints record their listener host on ``app.state``.
    """
    hosts = (
        _get_app_bind_host(request),
        _get_scope_server_host(request),
    )
    for host in hosts:
        if host is None:
            continue
        if not is_loopback_host(host, allow_test_sentinel=True):
            return True
    return False
