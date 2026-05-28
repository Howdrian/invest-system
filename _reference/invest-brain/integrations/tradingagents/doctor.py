from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys

try:
    from provider_config import known_api_keys, provider_api_keys
    from run_sidecar import list_ollama_models
    from schemas import (
        ADAPTER_CACHE,
        PROJECT_ROOT,
        PROTECTED_PATHS,
        RESEARCH_ARCHIVE,
        assert_safe_output_path,
        load_env_files,
    )
except ImportError:  # pragma: no cover
    from .provider_config import known_api_keys, provider_api_keys
    from .run_sidecar import list_ollama_models
    from .schemas import (
        ADAPTER_CACHE,
        PROJECT_ROOT,
        PROTECTED_PATHS,
        RESEARCH_ARCHIVE,
        assert_safe_output_path,
        load_env_files,
    )


API_KEYS = known_api_keys()


def package_status() -> dict[str, Any]:
    try:
        version = importlib.metadata.version("tradingagents")
        return {"importable": True, "version": version}
    except importlib.metadata.PackageNotFoundError:
        return {"importable": False, "version": None}


def isolated_package_status() -> dict[str, Any]:
    python_path = ADAPTER_CACHE / "venv" / "bin" / "python"
    if not python_path.exists():
        return {"python": str(python_path), "exists": False, "importable": False, "version": None}
    code = "import importlib.metadata as m; print(m.version('tradingagents'))"
    try:
        result = subprocess.run(
            [str(python_path), "-c", code],
            check=True,
            text=True,
            capture_output=True,
        )
        return {
            "python": str(python_path),
            "exists": True,
            "importable": True,
            "version": result.stdout.strip(),
        }
    except subprocess.CalledProcessError:
        return {"python": str(python_path), "exists": True, "importable": False, "version": None}


def api_key_status() -> dict[str, bool]:
    return {key: bool(os.getenv(key)) for key in API_KEYS}


def ollama_status() -> dict[str, Any]:
    binary = shutil.which("ollama")
    models = sorted(list_ollama_models()) if binary else []
    return {
        "installed": bool(binary),
        "binary": binary,
        "models": models,
        "model_count": len(models),
    }


def boundary_status() -> dict[str, Any]:
    allowed_probe = RESEARCH_ARCHIVE / "2099-01-01-doctor-probe" / "probe.txt"
    adapter_probe = ADAPTER_CACHE / "doctor-probe.txt"
    protected_results = {}
    for protected in sorted(PROTECTED_PATHS):
        try:
            assert_safe_output_path(protected)
            protected_results[str(protected)] = "unexpectedly_allowed"
        except Exception:
            protected_results[str(protected)] = "blocked"

    allowed_ok = True
    adapter_ok = True
    try:
        assert_safe_output_path(allowed_probe)
    except Exception:
        allowed_ok = False
    try:
        assert_safe_output_path(adapter_probe)
    except Exception:
        adapter_ok = False

    return {
        "research_archive_allowed": allowed_ok,
        "adapter_cache_allowed": adapter_ok,
        "protected_paths": protected_results,
    }


def collect_status() -> dict[str, Any]:
    loaded_env_files = load_env_files()
    keys = api_key_status()
    provider_key_present = any(keys[key] for key in provider_api_keys())
    status = {
        "project_root": str(PROJECT_ROOT),
        "loaded_env_files": [str(path) for path in loaded_env_files],
        "tradingagents_package": package_status(),
        "isolated_tradingagents_package": isolated_package_status(),
        "api_keys_present": keys,
        "ollama": ollama_status(),
        "provider_key_present": provider_key_present,
        "boundary": boundary_status(),
    }
    package_ready = (
        status["tradingagents_package"]["importable"]
        or status["isolated_tradingagents_package"]["importable"]
    )
    protected_bad = [
        path for path, result in status["boundary"]["protected_paths"].items()
        if result != "blocked"
    ]
    readiness_blockers: list[str] = []
    next_actions: list[str] = []
    if not package_ready:
        readiness_blockers.append("TradingAgents package is not importable.")
        next_actions.append("Run integrations/tradingagents/setup_env.py to prepare the isolated environment.")
    if not provider_key_present:
        readiness_blockers.append("No cloud LLM provider key is present.")
        next_actions.append("Set one provider key in .env, for example OPENAI_API_KEY or DEEPSEEK_API_KEY.")
        if status["ollama"]["installed"] and status["ollama"]["model_count"] == 0:
            readiness_blockers.append("Ollama is installed but no local model is available.")
            next_actions.append("Run ollama pull <model>, then use --llm-provider ollama --quick-model <model> --deep-model <model>.")
    if not status["boundary"]["research_archive_allowed"]:
        readiness_blockers.append("Research archive output path is not allowed.")
    if not status["boundary"]["adapter_cache_allowed"]:
        readiness_blockers.append("Adapter cache output path is not allowed.")
    if protected_bad:
        readiness_blockers.append("At least one protected path is not blocked.")
    status["ready_for_real_sidecar_run"] = (
        package_ready
        and provider_key_present
        and status["boundary"]["research_archive_allowed"]
        and status["boundary"]["adapter_cache_allowed"]
        and not protected_bad
    )
    status["readiness_blockers"] = readiness_blockers
    status["next_actions"] = next_actions
    return status


def render_markdown(status: dict[str, Any]) -> str:
    package = status["tradingagents_package"]
    isolated = status["isolated_tradingagents_package"]
    keys = status["api_keys_present"]
    key_lines = "\n".join(f"- `{key}`: {'present' if present else 'absent'}" for key, present in keys.items())
    env_files = status.get("loaded_env_files") or []
    env_text = "\n".join(f"- `{path}`" for path in env_files) if env_files else "- none"
    ollama = status["ollama"]
    ollama_models = ", ".join(f"`{model}`" for model in ollama["models"]) if ollama["models"] else "none"
    protected_bad = [
        path for path, result in status["boundary"]["protected_paths"].items()
        if result != "blocked"
    ]
    protected_text = "- all protected paths blocked" if not protected_bad else "\n".join(f"- NOT BLOCKED: {p}" for p in protected_bad)
    blockers = status.get("readiness_blockers") or []
    blocker_text = "\n".join(f"- {item}" for item in blockers) if blockers else "- none"
    actions = status.get("next_actions") or []
    action_text = "\n".join(f"- {item}" for item in actions) if actions else "- none"
    return f"""# TradingAgents Doctor

## Summary

- TradingAgents importable: `{package["importable"]}`
- TradingAgents version: `{package["version"]}`
- Isolated TradingAgents importable: `{isolated["importable"]}`
- Isolated TradingAgents version: `{isolated["version"]}`
- Isolated Python: `{isolated["python"]}`
- Provider key present: `{status["provider_key_present"]}`
- Ready for real sidecar run: `{status["ready_for_real_sidecar_run"]}`

## API Keys

{key_lines}

## Env Files

{env_text}

## Ollama

- Installed: `{ollama["installed"]}`
- Model count: `{ollama["model_count"]}`
- Models: {ollama_models}

## Boundary

- Research archive output allowed: `{status["boundary"]["research_archive_allowed"]}`
- Adapter cache output allowed: `{status["boundary"]["adapter_cache_allowed"]}`
{protected_text}

## Readiness Blockers

{blocker_text}

## Next Actions

{action_text}
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check TradingAgents sidecar readiness.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args(argv)
    status = collect_status()
    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(status))
    return 0 if status["boundary"]["research_archive_allowed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
