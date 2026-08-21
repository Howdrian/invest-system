from types import SimpleNamespace
from unittest.mock import patch

import pytest


def test_direct_server_defaults_to_configured_loopback(monkeypatch):
    import server

    monkeypatch.setattr(
        server,
        "config",
        SimpleNamespace(webui_host="127.0.0.1", webui_port=18000),
    )

    assert server._resolve_server_bind() == ("127.0.0.1", 18000)


def test_direct_server_refuses_public_bind_without_auth(monkeypatch):
    import server

    monkeypatch.setattr(
        server,
        "config",
        SimpleNamespace(webui_host="0.0.0.0", webui_port=8000),
    )

    with patch("src.auth.is_auth_enabled", return_value=False):
        with pytest.raises(RuntimeError, match="Refusing a non-loopback API bind"):
            server._resolve_server_bind()


def test_direct_server_allows_authenticated_public_bind(monkeypatch):
    import server

    monkeypatch.setattr(
        server,
        "config",
        SimpleNamespace(webui_host="0.0.0.0", webui_port=8000),
    )

    with patch("src.auth.is_auth_enabled", return_value=True), \
         patch("src.auth.has_stored_password", return_value=True):
        assert server._resolve_server_bind() == ("0.0.0.0", 8000)


def test_direct_server_refuses_public_bind_before_password_setup(monkeypatch):
    import server

    monkeypatch.setattr(
        server,
        "config",
        SimpleNamespace(webui_host="0.0.0.0", webui_port=8000),
    )

    with patch("src.auth.is_auth_enabled", return_value=True), \
         patch("src.auth.has_stored_password", return_value=False):
        with pytest.raises(RuntimeError, match="without a stored admin password"):
            server._resolve_server_bind()


def test_legacy_webui_entrypoint_uses_shared_public_bind_guard(monkeypatch):
    import webui

    monkeypatch.setenv("WEBUI_HOST", "0.0.0.0")
    monkeypatch.setenv("WEBUI_PORT", "18000")

    with patch("src.auth.is_auth_enabled", return_value=True), \
         patch("src.auth.has_stored_password", return_value=False):
        with pytest.raises(RuntimeError, match="without a stored admin password"):
            webui._resolve_webui_bind()


def test_legacy_webui_entrypoint_allows_initialized_public_auth(monkeypatch):
    import webui

    monkeypatch.setenv("WEBUI_HOST", "0.0.0.0")
    monkeypatch.setenv("WEBUI_PORT", "18000")

    with patch("src.auth.is_auth_enabled", return_value=True), \
         patch("src.auth.has_stored_password", return_value=True):
        assert webui._resolve_webui_bind() == ("0.0.0.0", 18000)
