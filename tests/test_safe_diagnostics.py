from src.safe_diagnostics import sanitize_diagnostic_text


def test_safe_diagnostics_redacts_headers_assignments_and_token_shapes():
    raw = (
        "Authorization: Bearer bearer-secret Cookie=session-secret "
        "OPENAI_API_KEY=openai-secret GEMINI_API_KEY:gemini-secret "
        "DEEPSEEK_API_KEY=deepseek-secret token=plain-token "
        "sk-1234567890abcdefghijklmnop"
    )

    sanitized = sanitize_diagnostic_text(raw, max_len=1000)

    for secret in (
        "bearer-secret",
        "session-secret",
        "openai-secret",
        "gemini-secret",
        "deepseek-secret",
        "plain-token",
        "sk-1234567890abcdefghijklmnop",
    ):
        assert secret not in sanitized
    assert "Authorization: <redacted>" in sanitized
    assert "OPENAI_API_KEY=<redacted>" in sanitized
    assert "GEMINI_API_KEY:<redacted>" in sanitized


def test_safe_diagnostics_redacts_webhooks_userinfo_and_query_credentials():
    raw = (
        "https://user:pass@example.test/path "
        "https://hooks.slack.com/services/T/B/secret-value "
        "https://discord.com/api/webhooks/123/secret-value "
        "https://api.example.test/data?symbol=AAPL&apikey=query-secret"
    )

    sanitized = sanitize_diagnostic_text(raw, max_len=1000)

    assert "user:pass" not in sanitized
    assert "secret-value" not in sanitized
    assert "query-secret" not in sanitized
    assert "https://<redacted>:<redacted>@example.test/path" in sanitized
    assert sanitized.count("<redacted-url>") == 2
    assert "apikey=<redacted>" in sanitized


def test_department_error_text_uses_public_diagnostic_sanitizer():
    from src.daily_department_llm import _error_text

    error = RuntimeError(
        "provider failed Authorization: Bearer canary-bearer "
        "API_KEY=canary-api-key https://user:pass@example.test/path"
    )

    sanitized = _error_text(error)

    for secret in ("canary-bearer", "canary-api-key", "user:pass"):
        assert secret not in sanitized


def test_safe_diagnostics_redacts_complete_multi_cookie_headers():
    raw = (
        "Cookie: theme=dark; sessionid=TOP-SECRET-COOKIE; foo=bar\n"
        "Authorization: Bearer first-secret extra-token-that-must-not-leak"
    )

    sanitized = sanitize_diagnostic_text(raw, max_len=1000)

    for secret in (
        "theme=dark",
        "TOP-SECRET-COOKIE",
        "foo=bar",
        "first-secret",
        "extra-token-that-must-not-leak",
    ):
        assert secret not in sanitized
    assert sanitized.count("<redacted>") == 2


def test_safe_diagnostics_redacts_structured_header_values():
    canary = "TOP-SECRET-STRUCTURED-COOKIE"
    raw_values = (
        {"Cookie": f"theme=dark; sessionid={canary}"},
        f'{{"Set-Cookie":"sessionid={canary}; HttpOnly"}}',
        f"headers={{'Authorization': 'Bearer {canary}', 'status': 401}}",
    )

    for raw in raw_values:
        sanitized = sanitize_diagnostic_text(raw, max_len=1000)
        assert canary not in sanitized
        assert "<redacted>" in sanitized
