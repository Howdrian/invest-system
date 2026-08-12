# -*- coding: utf-8 -*-
"""Static checks for LLM provider channel mappings in 00-daily-analysis.yml."""

from __future__ import annotations

import re
from pathlib import Path

import yaml


ROOT_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = ROOT_DIR / "apps/dsa-web/src/components/settings/llmProviderTemplates.ts"
WORKFLOW_PATH = ROOT_DIR / ".github/workflows/00-daily-analysis.yml"
ENV_EXAMPLE_PATH = ROOT_DIR / ".env.example"

EXPECTED_TEMPLATE_CHANNELS = {
    "aihubmix",
    "deepseek",
    "dashscope",
    "zhipu",
    "moonshot",
    "minimax",
    "volcengine",
    "siliconflow",
    "openrouter",
    "gemini",
    "anthropic",
    "openai",
    "ollama",
}


def _extract_provider_templates() -> dict[str, str]:
    content = TEMPLATE_PATH.read_text(encoding="utf-8")
    matches = re.findall(
        r"channelId:\s*'(?P<channel>[^']+)'.*?baseUrl:\s*'(?P<base_url>[^']*)'",
        content,
        flags=re.DOTALL,
    )
    assert matches, "No provider channelId entries were found in llmProviderTemplates.ts"

    templates = {channel: base_url for channel, base_url in matches if channel != "custom"}
    assert EXPECTED_TEMPLATE_CHANNELS.issubset(templates.keys())
    assert "ark" not in templates
    return templates


def _load_step_env(step_name: str) -> dict[str, str]:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = workflow["jobs"]["analyze"]["steps"]
    analyze_step = next((step for step in steps if step.get("name") == step_name), None)
    available_step_names = [step.get("name", "<unnamed>") for step in steps]
    assert analyze_step is not None, (
        "Expected 00-daily-analysis.yml job analyze to include a step named "
        f"'{step_name}'; available step names: {available_step_names}"
    )
    return analyze_step["env"]


def _load_daily_analysis_env() -> dict[str, str]:
    return _load_step_env("执行股票分析")


def test_daily_analysis_maps_all_provider_template_channels() -> None:
    templates = _extract_provider_templates()
    env = _load_daily_analysis_env()

    for channel in templates:
        prefix = f"LLM_{channel.upper()}_"
        for suffix in (
            "PROTOCOL",
            "API_SURFACE",
            "BASE_URL",
            "API_KEY",
            "API_KEYS",
            "MODELS",
            "ENABLED",
            "EXTRA_HEADERS",
        ):
            assert f"{prefix}{suffix}" in env

    assert not any(key.startswith("LLM_ARK_") for key in env)


def test_reports_step_reuses_daily_analysis_channel_routing_contract() -> None:
    channels = set(_extract_provider_templates()) | {"primary", "secondary", "hermes", "anspire"}
    analyze_env = _load_daily_analysis_env()
    reports_env = _load_step_env("生成静态报告中心")

    expected_keys = {"LLM_CHANNELS"}
    for channel in channels:
        expected_keys.update(
            key
            for suffix in (
                "PROTOCOL", "API_SURFACE", "BASE_URL", "API_KEY", "API_KEYS",
                "MODELS", "ENABLED", "EXTRA_HEADERS",
            )
            if (key := f"LLM_{channel.upper()}_{suffix}") in analyze_env
        )

    for key in expected_keys:
        assert reports_env[key] == analyze_env[key]

    for key in (
        "LITELLM_CONFIG",
        "LITELLM_CONFIG_YAML",
        "LITELLM_MODEL",
        "LITELLM_FALLBACK_MODELS",
    ):
        assert reports_env[key] == analyze_env[key]

    assert reports_env["AGENT_LITELLM_MODEL"] == analyze_env["AGENT_LITELLM_MODEL"]
    assert "RESEARCH_AGENT_LITELLM_MODEL" not in reports_env


def test_reports_step_reuses_legacy_llm_provider_contract() -> None:
    analyze_env = _load_daily_analysis_env()
    reports_env = _load_step_env("生成静态报告中心")

    for key in (
        "LITELLM_API_KEY",
        "GEMINI_API_KEY", "GEMINI_API_KEYS", "GEMINI_MODEL", "GEMINI_MODEL_FALLBACK",
        "AIHUBMIX_KEY",
        "OPENAI_API_KEY", "OPENAI_API_KEYS", "OPENAI_BASE_URL", "OPENAI_MODEL",
        "DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS",
        "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS", "ANTHROPIC_MODEL",
        "ANSPIRE_API_KEYS", "ANSPIRE_LLM_BASE_URL", "ANSPIRE_LLM_MODEL", "ANSPIRE_LLM_ENABLED",
    ):
        assert reports_env[key] == analyze_env[key]


def test_reports_step_reuses_universe_and_realtime_provider_contract() -> None:
    analyze_env = _load_daily_analysis_env()
    reports_env = _load_step_env("生成静态报告中心")

    expected_keys = {"STOCK_LIST_CONFIG", "REALTIME_SOURCE_PRIORITY"}
    expected_keys.update(key for key in analyze_env if key.startswith("TICKFLOW_"))
    expected_keys.update(key for key in analyze_env if key.startswith("LONGBRIDGE_"))
    for key in expected_keys:
        assert reports_env[key] == analyze_env[key]

    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    reports_script = workflow_text.split("- name: 生成静态报告中心", 1)[1].split("- name: 上传 GitHub Pages 产物", 1)[0]
    assert 'export STOCK_LIST="$STOCK_LIST_CONFIG"' in reports_script


def test_reports_step_materializes_litellm_yaml_atomically_without_logging_content() -> None:
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    reports_script = workflow_text.split("- name: 生成静态报告中心", 1)[1].split("- name: 上传 GitHub Pages 产物", 1)[0]

    assert 'printf \'%s\\n\' "$LITELLM_CONFIG_YAML" > "$LITELLM_CONFIG_TMP"' in reports_script
    assert 'mktemp "$(dirname "$LITELLM_CONFIG")/.litellm-config.XXXXXX"' in reports_script
    assert 'mv -f -- "$LITELLM_CONFIG_TMP" "$LITELLM_CONFIG"' in reports_script
    assert 'echo "$LITELLM_CONFIG_YAML"' not in reports_script
    assert reports_script.index("LITELLM_CONFIG_TMP=") < reports_script.index("scripts/run_research_daily_local.sh")


def test_daily_analysis_keeps_channel_secrets_in_secrets_context() -> None:
    templates = _extract_provider_templates()
    env = _load_daily_analysis_env()

    for channel in templates:
        upper = channel.upper()
        for suffix in ("API_KEY", "API_KEYS"):
            key = f"LLM_{upper}_{suffix}"
            assert env[key] == f"${{{{ secrets.{key} }}}}"

        for suffix in ("PROTOCOL", "API_SURFACE", "BASE_URL", "MODELS", "ENABLED", "EXTRA_HEADERS"):
            key = f"LLM_{upper}_{suffix}"
            assert f"vars.{key}" in env[key]
            assert f"secrets.{key}" in env[key]


def test_daily_analysis_maps_usage_hmac_config_safely() -> None:
    env = _load_daily_analysis_env()

    assert env["LLM_USAGE_HMAC_SECRET"] == "${{ secrets.LLM_USAGE_HMAC_SECRET }}"
    assert "vars.LLM_USAGE_HMAC_SECRET" not in env["LLM_USAGE_HMAC_SECRET"]
    assert "vars.LLM_USAGE_HMAC_KEY_VERSION" in env["LLM_USAGE_HMAC_KEY_VERSION"]
    assert "secrets.LLM_USAGE_HMAC_KEY_VERSION" in env["LLM_USAGE_HMAC_KEY_VERSION"]


def test_daily_analysis_maps_prompt_cache_config() -> None:
    env = _load_daily_analysis_env()

    for key in (
        "LLM_PROMPT_CACHE_TELEMETRY_ENABLED",
        "LLM_PROMPT_CACHE_HINTS_ENABLED",
        "LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL",
    ):
        assert key in env
        assert f"vars.{key}" in env[key]
        assert f"secrets.{key}" in env[key]


def test_daily_analysis_maps_generation_backend_runtime_config() -> None:
    env = _load_daily_analysis_env()

    for key in (
        "GENERATION_BACKEND",
        "GENERATION_FALLBACK_BACKEND",
        "GENERATION_BACKEND_TIMEOUT_SECONDS",
        "GENERATION_BACKEND_MAX_OUTPUT_BYTES",
        "GENERATION_BACKEND_MAX_CONCURRENCY",
        "LOCAL_CLI_BACKEND_MAX_CONCURRENCY",
        "AGENT_GENERATION_BACKEND",
    ):
        assert key in env
        assert f"vars.{key}" in env[key]
        assert f"secrets.{key}" in env[key]


def test_daily_analysis_generation_fallback_defaults_to_litellm() -> None:
    env = _load_daily_analysis_env()
    expression = env["GENERATION_FALLBACK_BACKEND"]

    assert expression == (
        "${{ vars.GENERATION_FALLBACK_BACKEND || "
        "secrets.GENERATION_FALLBACK_BACKEND || 'litellm' }}"
    )


def test_env_example_includes_provider_template_channel_examples() -> None:
    templates = _extract_provider_templates()
    env_example = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")

    for channel, base_url in templates.items():
        upper = channel.upper()
        assert f"LLM_CHANNELS={channel}" in env_example
        assert f"LLM_{upper}_MODELS=" in env_example

        if channel != "ollama":
            assert f"LLM_{upper}_API_KEY=" in env_example
        if base_url:
            assert f"LLM_{upper}_BASE_URL=" in env_example
        if channel != "ollama":
            assert f"LLM_{upper}_PROTOCOL=" in env_example

    assert "LLM_CHANNELS=ark" not in env_example
    assert "LLM_ARK_" not in env_example
