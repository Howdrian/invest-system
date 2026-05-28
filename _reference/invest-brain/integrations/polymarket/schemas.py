from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import json
import re

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_ARCHIVE = PROJECT_ROOT / "research" / "archive"
ADAPTER_CACHE = PROJECT_ROOT / "integrations" / "polymarket" / ".cache"
PULSE_PATH = PROJECT_ROOT / "state" / "prediction-market-pulse.md"

PROTECTED_PATHS = {
    PROJECT_ROOT / "state" / "portfolio.md",
    PROJECT_ROOT / "state" / "market-pulse.md",
    PROJECT_ROOT / "state" / "watchlist.md",
    PROJECT_ROOT / "trades" / "trade-log.md",
    PROJECT_ROOT / "agents" / "scoring-card.md",
    PROJECT_ROOT / "agents" / "red-team-protocol.md",
}

SLUG_RE = re.compile(r"[^a-z0-9-]+")


class PolymarketIntegrationError(RuntimeError):
    """Raised when the read-only integration would violate project boundaries."""


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def archive_slug(value: str) -> str:
    slug = value.strip().lower().replace("_", "-").replace(" ", "-")
    slug = SLUG_RE.sub("-", slug).strip("-")
    if not slug:
        raise PolymarketIntegrationError("empty archive slug")
    return slug[:96]


def archive_dir_for(analysis_date: str, topic: str = "polymarket-signal") -> Path:
    out = RESEARCH_ARCHIVE / f"{analysis_date}-{archive_slug(topic)}"
    assert_safe_output_path(out)
    return out


def assert_safe_output_path(path: Path, *, allow_pulse: bool = False) -> None:
    resolved = path.resolve()
    if allow_pulse and resolved == PULSE_PATH.resolve():
        return

    allowed = is_relative_to(resolved, RESEARCH_ARCHIVE) or is_relative_to(resolved, ADAPTER_CACHE)
    if not allowed:
        raise PolymarketIntegrationError(f"Output path is outside allowed roots: {path}")

    for protected in PROTECTED_PATHS:
        if resolved == protected.resolve():
            raise PolymarketIntegrationError(f"Refusing to write protected file: {path}")


def write_text_safe(path: Path, content: str, *, allow_pulse: bool = False) -> None:
    assert_safe_output_path(path, allow_pulse=allow_pulse)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json_safe(path: Path, payload: Any) -> None:
    assert_safe_output_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass
class MarketSource:
    source: str = "polymarket"
    event_id: str | None = None
    market_id: str | None = None
    condition_id: str | None = None
    slug: str | None = None
    url: str | None = None


@dataclass
class OrderBookSnapshot:
    bid: float | None = None
    ask: float | None = None
    mid: float | None = None
    spread: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    book_hash: str | None = None
    retrieved_at: str = field(default_factory=utc_now)


@dataclass
class PredictionMarketSignal:
    source: MarketSource
    question: str
    event_title: str | None
    event_category: str
    yes_probability: float | None
    outcome_prices: list[float]
    outcomes: list[str]
    volume: float
    volume_24h: float
    liquidity: float
    end_date: str | None
    updated_at: str | None
    active: bool
    closed: bool
    accepting_orders: bool
    orderbook: OrderBookSnapshot = field(default_factory=OrderBookSnapshot)
    recent_trades: list[dict[str, Any]] = field(default_factory=list)
    quality_score: float = 0.0
    quality_bucket: str = "low"
    recommended_weight: float = 0.0
    notes: list[str] = field(default_factory=list)
    retrieved_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SignalRun:
    schema: str
    generated_at: str
    analysis_date: str
    topic: str
    keywords: list[str]
    signals: list[PredictionMarketSignal]
    rejected: list[dict[str, Any]] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["signals"] = [signal.to_dict() for signal in self.signals]
        return data
