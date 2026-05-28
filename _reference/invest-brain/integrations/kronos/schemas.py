#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class KronosForecastRequest:
    symbol: str
    analysis_date: str
    lookback: int = 256
    pred_len: int = 20
    model: str = "mini"
    interval: str = "1d"
    range_: str = "2y"
    seed: int = 123
    temperature: float = 1.0
    top_k: int = 1
    top_p: float = 1.0
    sample_count: int = 1
    data_source: str = "Yahoo chart public endpoint"
    allow_download: bool = False
    kronos_repo: str | None = None
    model_revision: str | None = None
    tokenizer_revision: str | None = None


@dataclass
class KronosForecastResult:
    schema: str = "kronos_forecast_v1"
    symbol: str = ""
    analysis_date: str = ""
    status: str = "degraded"  # ok | degraded | unavailable
    usability: str = "degraded"  # usable | degraded | unavailable
    model_available: bool = False
    model_name: str = ""
    tokenizer_name: str = ""
    model_revision: str = "not-pinned"
    tokenizer_revision: str = "not-pinned"
    checksum: str = "unknown"
    device: str = "not-used"
    lookback: int = 0
    pred_len: int = 0
    seed: int = 123
    temperature: float = 1.0
    top_k: int = 1
    top_p: float = 1.0
    sample_count: int = 1
    input_columns: list[str] = field(default_factory=lambda: ["open", "high", "low", "close", "volume", "amount"])
    amount_missing: bool = True
    amount_policy: str = "amount unavailable from source; close*volume proxy is marked and never treated as real turnover"
    data_source: str = ""
    data_points: int = 0
    missing_bars_count: int = 0
    latest_close: float | None = None
    predicted_close_last: float | None = None
    forecast_start_timestamp: str | None = None
    forecast_end_timestamp: str | None = None
    forecast_direction: str = "uncertain"  # up | down | flat | uncertain
    forecast_change_pct: float | None = None
    confidence: float = 0.0
    scoring_impact: int = 0
    protected_writeback: bool = False
    runtime_seconds: float = 0.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    data_constraints: list[str] = field(default_factory=list)
    output_files: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
