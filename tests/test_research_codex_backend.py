"""Codex research routing must not invoke API model selection."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src import daily_department_llm as departments
from src.llm.generation_backend import GenerationError
from src.llm.local_cli_backend import LocalCliGenerationBackend


def test_codex_model_and_effort_are_explicit_argv(tmp_path):
    backend = LocalCliGenerationBackend(SimpleNamespace(
        codex_cli_model="example-model", codex_cli_reasoning_effort="high",
    ), preset_id="codex_cli")
    _, args, _ = backend._resolve_command()
    args, _ = backend._build_runtime_argv(args, str(tmp_path))
    assert args[args.index("--model") + 1] == "example-model"
    assert 'model_reasoning_effort="high"' in args
    assert args[-1] == "-"
    assert "read-only" in args


@pytest.mark.parametrize("field,value", [
    ("codex_cli_model", "--dangerously-bypass-approvals-and-sandbox"),
    ("codex_cli_model", "model;echo hacked"),
    ("codex_cli_reasoning_effort", "unknown-effort"),
])
def test_codex_unsafe_options_rejected(tmp_path, field, value):
    backend = LocalCliGenerationBackend(SimpleNamespace(**{field: value}), preset_id="codex_cli")
    _, args, _ = backend._resolve_command()
    with pytest.raises(GenerationError):
        backend._build_runtime_argv(args, str(tmp_path))


def test_research_codex_bypasses_api_model_smoke(monkeypatch):
    config = SimpleNamespace(agent_generation_backend="codex_cli",
                             codex_cli_model="example-model", codex_cli_reasoning_effort="high")
    monkeypatch.setattr(departments, "_load_lightweight_llm_config", lambda: config)
    smoke = Mock(side_effect=AssertionError("API smoke must not run"))
    monkeypatch.setattr(departments, "_select_agent_model", smoke)
    backend, selection = departments.build_default_llm_backend_with_selection()
    assert backend.backend_id == "codex_cli"
    assert selection["requestedModel"] == "example-model"
    assert selection["reasoningEffort"] == "high"
    assert selection["candidates"] == []
    smoke.assert_not_called()


def test_research_options_override_general_cli_config(monkeypatch):
    monkeypatch.setattr(departments, "_load_lightweight_env_values", lambda: {
        "RESEARCH_GENERATION_BACKEND": "codex_cli",
        "CODEX_CLI_MODEL": "general-model",
        "RESEARCH_CODEX_MODEL": "research-model",
        "RESEARCH_CODEX_REASONING_EFFORT": "xhigh",
        "GENERATION_BACKEND_TIMEOUT_SECONDS": "300",
    })
    for key in ("RESEARCH_GENERATION_BACKEND", "RESEARCH_CODEX_MODEL", "RESEARCH_CODEX_REASONING_EFFORT"):
        monkeypatch.delenv(key, raising=False)
    config = departments._load_lightweight_llm_config()
    assert config.agent_generation_backend == "codex_cli"
    assert config.codex_cli_model == "research-model"
    assert config.codex_cli_reasoning_effort == "xhigh"
    assert int(config.generation_backend_timeout_seconds) == 300


def test_isolated_codex_does_not_inherit_plugins_or_tools(tmp_path):
    backend = LocalCliGenerationBackend(SimpleNamespace(codex_cli_isolated=True), preset_id="codex_cli")
    _, args, _ = backend._resolve_command()
    args, _ = backend._build_runtime_argv(args, str(tmp_path))
    assert "--ignore-user-config" in args
    for feature in ("hooks", "shell_tool", "plugins", "apps", "multi_agent"):
        assert f"features.{feature}=false" in args
    assert 'model_provider="openai"' in args
    assert "features.skip_host_skill_discovery=true" in args


def test_research_configuration_fields_are_editable():
    from src.core.config_registry import _FIELD_DEFINITIONS
    for field in ("CODEX_CLI_MODEL", "CODEX_CLI_REASONING_EFFORT", "RESEARCH_GENERATION_BACKEND",
                  "RESEARCH_CODEX_MODEL", "RESEARCH_CODEX_REASONING_EFFORT"):
        assert _FIELD_DEFINITIONS[field]["is_editable"]
        assert not _FIELD_DEFINITIONS[field]["is_sensitive"]


def test_codex_banner_is_not_an_approval_request():
    backend = LocalCliGenerationBackend(SimpleNamespace(), preset_id="codex_cli")
    error = backend._non_zero_exit_error(1, "", "approval: never\nERROR: connection refused", {})
    assert error.error_code.value == "non_zero_exit"
    assert "connection refused" in error.details["stderr_tail"]


@pytest.mark.parametrize("available,expected", [(True, "configured"), (False, "needs_action")])
def test_setup_status_uses_codex_chat_capability_not_api_keys(monkeypatch, available, expected):
    from src.services.system_config_service import SystemConfigService
    status = Mock()
    status.get_status.return_value = {"available": available, "message": "CLI unavailable"}
    monkeypatch.setattr("src.services.system_config_service.AgentBackendStatusService", lambda **kw: status)
    service = object.__new__(SystemConfigService)
    result = service._build_setup_agent_llm_check(
        {"AGENT_BACKEND": "codex_app_server", "GENERATION_BACKEND": "codex_cli"}, {},
    )
    assert result["status"] == expected
    assert "LiteLLM" not in result["message"]


def test_settings_smoke_preserves_codex_model_and_effort():
    from src.services.generation_backend_status_service import GenerationBackendStatusService
    config = GenerationBackendStatusService(effective_map={
        "GENERATION_BACKEND": "codex_cli", "CODEX_CLI_MODEL": "example-model",
        "CODEX_CLI_REASONING_EFFORT": "high", "GENERATION_FALLBACK_BACKEND": "",
    }).build_effective_config()
    assert config.codex_cli_model == "example-model"
    assert config.codex_cli_reasoning_effort == "high"
    assert config.generation_fallback_backend == ""


def test_resume_fingerprint_tracks_effective_inputs_not_smoke_timing():
    from src.daily_department_llm import _department_input_fingerprint as fingerprint
    base = fingerprint('evidence A', 'SOP', {'codex_cli_model': 'model-a', 'codex_cli_reasoning_effort': 'high'}, {'selectedModel': 'model-a'})
    assert base == fingerprint('evidence A', 'SOP', {'codex_cli_model': 'model-a', 'codex_cli_reasoning_effort': 'high'}, {'selectedModel': 'model-a', 'duration': 900})
    assert base != fingerprint('evidence B', 'SOP', {'codex_cli_model': 'model-a', 'codex_cli_reasoning_effort': 'high'}, {'selectedModel': 'model-a'})
    assert base != fingerprint('evidence A', 'new SOP', {'codex_cli_model': 'model-a', 'codex_cli_reasoning_effort': 'high'}, {'selectedModel': 'model-a'})
    assert base != fingerprint('evidence A', 'SOP', {'codex_cli_model': 'model-b', 'codex_cli_reasoning_effort': 'high'}, {'selectedModel': 'model-a'})
    assert base != fingerprint('evidence A', 'SOP', {'codex_cli_model': 'model-a', 'codex_cli_reasoning_effort': 'low'}, {'selectedModel': 'model-a'})
