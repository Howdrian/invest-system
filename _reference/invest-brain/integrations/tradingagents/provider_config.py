from __future__ import annotations


PROVIDER_KEYS = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "xai": "XAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "dashscope": "DASHSCOPE_API_KEY",
    "glm": "ZHIPU_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "azure": "AZURE_OPENAI_API_KEY",
    "azure_openai": "AZURE_OPENAI_API_KEY",
}

DATA_KEYS = {
    "alpha_vantage": "ALPHA_VANTAGE_API_KEY",
}


def normalize_provider(provider: str) -> str:
    return provider.strip().lower().replace("-", "_")


def required_key_for_provider(provider: str) -> str | None:
    normalized = normalize_provider(provider)
    if normalized == "ollama":
        return None
    return PROVIDER_KEYS.get(normalized, f"{normalized.upper()}_API_KEY")


def known_api_keys() -> list[str]:
    return sorted(set(PROVIDER_KEYS.values()) | set(DATA_KEYS.values()))


def provider_api_keys() -> list[str]:
    return sorted(set(PROVIDER_KEYS.values()))
