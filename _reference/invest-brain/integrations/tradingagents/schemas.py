from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
import json
import os
import re


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_ARCHIVE = PROJECT_ROOT / "research" / "archive"
ADAPTER_CACHE = PROJECT_ROOT / "integrations" / "tradingagents" / ".cache"
ENV_FILE_CANDIDATES = [
    PROJECT_ROOT / ".env",
    PROJECT_ROOT / "integrations" / "tradingagents" / ".env",
    ADAPTER_CACHE / "upstream" / "TradingAgents" / ".env",
]

PROTECTED_PATHS = {
    PROJECT_ROOT / "state" / "portfolio.md",
    PROJECT_ROOT / "state" / "market-pulse.md",
    PROJECT_ROOT / "state" / "watchlist.md",
    PROJECT_ROOT / "trades" / "trade-log.md",
    PROJECT_ROOT / "AGENTS.md",
    PROJECT_ROOT / "CLAUDE.md",
    PROJECT_ROOT / "skill.md",
    PROJECT_ROOT / "memory.md",
}

PROTECTED_DIRS = {
    PROJECT_ROOT / "agents",
    PROJECT_ROOT / "frameworks",
    PROJECT_ROOT / "state",
    PROJECT_ROOT / "trades",
}

RATINGS = {"Buy", "Overweight", "Hold", "Underweight", "Sell"}
TICKER_RE = re.compile(r"^[A-Za-z0-9.^-]{1,32}$")


class IntegrationError(RuntimeError):
    """Raised when the sidecar would violate a project boundary."""


ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_env_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("export "):
        stripped = stripped[7:].strip()
    if "=" not in stripped:
        return None
    key, value = stripped.split("=", 1)
    key = key.strip()
    if not ENV_KEY_RE.match(key):
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return key, value


def load_env_files(paths: list[Path] | None = None) -> list[Path]:
    loaded: list[Path] = []
    for env_path in paths or ENV_FILE_CANDIDATES:
        if not env_path.exists():
            continue
        for line in env_path.read_text(encoding="utf-8").splitlines():
            parsed = parse_env_line(line)
            if parsed is None:
                continue
            key, value = parsed
            os.environ.setdefault(key, value)
        loaded.append(env_path)
    return loaded


@dataclass
class EvidenceClaim:
    claim: str
    type: str
    source_section: str
    evidence: str = ""
    confidence: str = "unverified_external"


@dataclass
class ExternalAgentEvidence:
    source: str
    ticker: str
    analysis_date: str
    rating: str | None = None
    claims: list[EvidenceClaim] = field(default_factory=list)
    risks: list[EvidenceClaim] = field(default_factory=list)
    catalysts: list[EvidenceClaim] = field(default_factory=list)
    suggested_entry: float | None = None
    suggested_stop: float | None = None
    unknowns: list[str] = field(default_factory=list)
    extraction_method: str = "heuristic_section_parser_v1"
    raw_sections: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write_json(self, path: Path) -> None:
        assert_safe_output_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


@dataclass
class SidecarMetadata:
    source: str
    ticker: str
    analysis_date: str
    mode: str
    output_dir: str
    created_date: str = field(default_factory=lambda: date.today().isoformat())
    notes: list[str] = field(default_factory=list)

    def write_json(self, path: Path) -> None:
        assert_safe_output_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def validate_ticker(ticker: str) -> str:
    value = ticker.strip()
    if not TICKER_RE.match(value):
        raise IntegrationError(f"Unsafe ticker: {ticker!r}")
    if value in {".", ".."} or "/" in value or "\\" in value:
        raise IntegrationError(f"Unsafe ticker path component: {ticker!r}")
    return value.upper()


def archive_slug(ticker: str) -> str:
    safe = validate_ticker(ticker)
    if safe.startswith("^"):
        safe = "INDEX-" + safe[1:]
    safe = safe.replace(".", "-").lower()
    safe = re.sub(r"[^a-z0-9-]+", "-", safe).strip("-")
    if not safe:
        raise IntegrationError(f"Could not build archive slug for ticker: {ticker!r}")
    return safe


def archive_dir_for(ticker: str, analysis_date: str, archive_root: Path | None = None) -> Path:
    root = archive_root or RESEARCH_ARCHIVE
    directory = root / f"{analysis_date}-tradingagents-{archive_slug(ticker)}"
    assert_safe_output_path(directory)
    return directory


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def assert_safe_output_path(path: Path) -> None:
    resolved = path.resolve()
    allowed = is_relative_to(resolved, RESEARCH_ARCHIVE) or is_relative_to(resolved, ADAPTER_CACHE)
    if not allowed:
        raise IntegrationError(f"Output path is outside allowed roots: {path}")

    for protected in PROTECTED_PATHS:
        if resolved == protected.resolve():
            raise IntegrationError(f"Refusing to write protected file: {path}")

    for protected_dir in PROTECTED_DIRS:
        if is_relative_to(resolved, protected_dir):
            raise IntegrationError(f"Refusing to write inside protected directory: {path}")


def write_text_safe(path: Path, content: str) -> None:
    assert_safe_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json_safe(path: Path, payload: dict[str, Any]) -> None:
    assert_safe_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
