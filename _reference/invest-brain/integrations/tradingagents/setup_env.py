from __future__ import annotations

from pathlib import Path
import argparse
import subprocess
import sys

try:
    from schemas import ADAPTER_CACHE, assert_safe_output_path
except ImportError:  # pragma: no cover
    from .schemas import ADAPTER_CACHE, assert_safe_output_path


REPO_URL = "https://github.com/TauricResearch/TradingAgents.git"
PINNED_COMMIT = "7e9e7b83c7fcc18d941300b253c6ed24d985788d"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd) if cwd else None, check=True)


def paths() -> dict[str, Path]:
    return {
        "upstream": ADAPTER_CACHE / "upstream" / "TradingAgents",
        "venv": ADAPTER_CACHE / "venv",
    }


def ensure_cache_paths() -> dict[str, Path]:
    ADAPTER_CACHE.mkdir(parents=True, exist_ok=True)
    result = paths()
    for path in result.values():
        assert_safe_output_path(path)
    return result


def ensure_upstream(repo_path: Path, force: bool = False) -> None:
    if repo_path.exists() and force:
        raise RuntimeError(
            "Refusing to delete existing upstream clone automatically. "
            "Move integrations/tradingagents/.cache/upstream/TradingAgents to trash first."
        )
    if not repo_path.exists():
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "clone", REPO_URL, str(repo_path)])

    run(["git", "fetch", "--tags", "origin"], cwd=repo_path)
    run(["git", "checkout", PINNED_COMMIT], cwd=repo_path)


def ensure_venv(venv_path: Path) -> Path:
    python_path = venv_path / "bin" / "python"
    if not python_path.exists():
        run([sys.executable, "-m", "venv", str(venv_path)])
    return python_path


def install_package(python_path: Path, repo_path: Path) -> None:
    run([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
    run([str(python_path), "-m", "pip", "install", "-e", str(repo_path)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare isolated TradingAgents sidecar environment.")
    parser.add_argument("--clone-only", action="store_true", help="Clone and pin upstream source without installing Python deps.")
    parser.add_argument("--force", action="store_true", help="Reserved; never deletes automatically.")
    args = parser.parse_args(argv)

    p = ensure_cache_paths()
    ensure_upstream(p["upstream"], force=args.force)
    python_path = ensure_venv(p["venv"])
    if not args.clone_only:
        install_package(python_path, p["upstream"])

    print("\nEnvironment prepared:")
    print(f"- upstream: {p['upstream']}")
    print(f"- python:   {python_path}")
    print("\nRun doctor with:")
    print(f"{python_path} integrations/tradingagents/doctor.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

