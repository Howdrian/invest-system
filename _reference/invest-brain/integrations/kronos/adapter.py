#!/usr/bin/env python3
from __future__ import annotations

import html
import hashlib
import importlib.util
import json
import math
import os
import random
import sys
import time
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore

try:
    from .schemas import KronosForecastRequest, KronosForecastResult
except ImportError:  # pragma: no cover
    from schemas import KronosForecastRequest, KronosForecastResult

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_ARCHIVE = PROJECT_ROOT / "research" / "archive"
MODEL_CACHE_DIR = PROJECT_ROOT / "research" / "cache" / "kronos_models"
USER_AGENT = "invest-brain-kronos-sidecar/0.1"

MODEL_IDS = {
    "mini": {
        "model": "NeoQuasar/Kronos-mini",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-2k",
        "context": 2048,
        "model_revision": "f4e68697d9d5aed55cef5c96aabc3376bcad9f81",
        "tokenizer_revision": "26966d0035065a0cae0ebad7af8ece35bc1fb51c",
    },
    "small": {
        "model": "NeoQuasar/Kronos-small",
        "tokenizer": "NeoQuasar/Kronos-Tokenizer-base",
        "context": 512,
        "model_revision": "901c26c1332695a2a8f243eb2f37243a37bea320",
        "tokenizer_revision": "0e0117387f39004a9016484a186a908917e22426",
    },
}

REQUIRED_IMPORTS = ["torch", "huggingface_hub", "safetensors", "pandas", "numpy"]


def archive_dir(analysis_date: str, topic: str) -> Path:
    slug = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in topic.lower()).strip("-") or "kronos-smoke"
    out = RESEARCH_ARCHIVE / f"{analysis_date}-{slug}"
    if not str(out.resolve()).startswith(str(RESEARCH_ARCHIVE.resolve())):
        raise RuntimeError("unsafe archive path")
    return out


def dependency_report() -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in REQUIRED_IMPORTS}


def infer_data_constraints(symbol: str) -> list[str]:
    s = symbol.upper()
    constraints = [
        "Yahoo daily bars are public-source snapshots, not production-grade audited market data.",
        "Corporate actions must distinguish adjusted vs raw close before any backtest or promotion.",
        "Missing bars, holidays, and source gaps are explicit risk inputs, not silently filled conviction.",
    ]
    if s.endswith(".SS") or s.endswith(".SZ"):
        constraints.extend([
            "A-share smoke must handle suspension days and limit-up/limit-down regimes before production use.",
            "A-share timezone/calendar differs from US daily bars.",
        ])
    elif s.endswith(".HK"):
        constraints.extend([
            "HK equities require HK calendar/timezone handling and HKD currency awareness.",
            "Southbound/liquidity effects are not captured by Kronos smoke input.",
        ])
    elif "-USD" in s or s.endswith("USDT") or s in {"BTC", "ETH"}:
        constraints.append("Crypto daily boundary and 24/7 trading calendar differ from equity sessions.")
    else:
        constraints.append("US equities/ETFs still require split/dividend handling before validation.")
    return constraints


def fetch_yahoo_ohlcv(symbol: str, range_: str = "2y", interval: str = "1d", timeout: int = 15) -> tuple[Any, dict[str, Any]]:
    if pd is None:
        raise RuntimeError("pandas is required to parse Yahoo chart data")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}?{urlencode({'range': range_, 'interval': interval})}"
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    raw = urlopen(req, timeout=timeout).read().decode("utf-8")
    payload = json.loads(raw)
    result = (payload.get("chart", {}).get("result") or [None])[0]
    if not result:
        error = payload.get("chart", {}).get("error")
        raise RuntimeError(f"no Yahoo chart result: {error}")
    timestamps = result.get("timestamp") or []
    quote_data = (result.get("indicators", {}).get("quote") or [{}])[0]
    rows = []
    missing = 0
    for i, ts in enumerate(timestamps):
        row = {"timestamps": datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)}
        bad = False
        for key in ["open", "high", "low", "close", "volume"]:
            values = quote_data.get(key) or []
            value = values[i] if i < len(values) else None
            if value is None or (isinstance(value, float) and math.isnan(value)):
                bad = True
            row[key] = value
        if bad:
            missing += 1
            continue
        row["amount"] = float(row["close"]) * float(row["volume"])
        rows.append(row)
    if not rows:
        raise RuntimeError("no complete OHLCV rows")
    df = pd.DataFrame(rows)
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    meta = {"url": url, "missing_bars_count": missing, "amount_missing": True, "source": "Yahoo chart public endpoint"}
    return df, meta


def _future_timestamps(last_ts: Any, pred_len: int, interval: str) -> Any:
    if pd is None:
        raise RuntimeError("pandas is required")
    last = pd.to_datetime(last_ts)
    if interval.endswith("d"):
        return pd.Series(pd.date_range(last + pd.Timedelta(days=1), periods=pred_len, freq="D"))
    if interval.endswith("h"):
        hours = int(interval[:-1] or "1")
        return pd.Series(pd.date_range(last + pd.Timedelta(hours=hours), periods=pred_len, freq=f"{hours}h"))
    return pd.Series(pd.date_range(last + pd.Timedelta(days=1), periods=pred_len, freq="D"))


def _direction(change_pct: float | None) -> str:
    if change_pct is None:
        return "uncertain"
    if change_pct > 1.0:
        return "up"
    if change_pct < -1.0:
        return "down"
    return "flat"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_real_kronos(req: KronosForecastRequest, df: Any) -> tuple[float | None, str, list[str], list[str], str, str, str, dict[str, Any]]:
    warnings: list[str] = []
    errors: list[str] = []
    ids = MODEL_IDS.get(req.model, MODEL_IDS["mini"])
    model_revision = req.model_revision or str(ids.get("model_revision") or "")
    tokenizer_revision = req.tokenizer_revision or str(ids.get("tokenizer_revision") or "")
    if not req.kronos_repo:
        errors.append("--kronos-repo or KRONOS_REPO_DIR is required for real Kronos smoke; project does not vendor upstream code")
        return None, "not-used", warnings, errors, "not-used", "not-used", "unknown", {}
    repo = Path(req.kronos_repo).expanduser().resolve()
    if not (repo / "model").exists():
        errors.append(f"Kronos repo model/ not found: {repo}")
        return None, "not-used", warnings, errors, "not-used", "not-used", "unknown", {}
    if not model_revision or not tokenizer_revision:
        errors.append("model/tokenizer revision is not pinned; pass --revision and --tokenizer-revision before real download/run")
        return None, "not-used", warnings, errors, "not-used", "not-used", "unknown", {}
    missing = [name for name, ok in dependency_report().items() if not ok]
    if missing:
        errors.append("missing Python dependencies: " + ", ".join(missing))
        return None, "not-used", warnings, errors, "not-used", "not-used", "unknown", {}
    sys.path.insert(0, str(repo))
    try:
        import torch  # type: ignore
        from huggingface_hub import snapshot_download  # type: ignore
        from model import Kronos, KronosPredictor, KronosTokenizer  # type: ignore
    except Exception as exc:  # pragma: no cover
        errors.append(f"failed to import Kronos runtime: {exc}")
        return None, "not-used", warnings, errors, "not-used", "not-used", "unknown", {}
    MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HOME", str(MODEL_CACHE_DIR))
    device = "cuda" if getattr(torch, "cuda", None) and torch.cuda.is_available() else "cpu"
    try:
        random.seed(req.seed)
        try:
            import numpy as np  # type: ignore
            np.random.seed(req.seed)
        except Exception:
            pass
        torch.manual_seed(req.seed)
        if getattr(torch.backends, "cudnn", None) and torch.backends.cudnn.is_available():
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
        tokenizer_path = Path(snapshot_download(
            repo_id=str(ids["tokenizer"]),
            revision=tokenizer_revision,
            cache_dir=str(MODEL_CACHE_DIR / "hub"),
            allow_patterns=["config.json", "model.safetensors"],
        ))
        model_path = Path(snapshot_download(
            repo_id=str(ids["model"]),
            revision=model_revision,
            cache_dir=str(MODEL_CACHE_DIR / "hub"),
            allow_patterns=["config.json", "model.safetensors"],
        ))
        checksum = (
            f"model:{_sha256(model_path / 'model.safetensors')};"
            f"tokenizer:{_sha256(tokenizer_path / 'model.safetensors')}"
        )
        tokenizer = KronosTokenizer.from_pretrained(str(tokenizer_path))
        model = Kronos.from_pretrained(str(model_path))
        if hasattr(model, "to"):
            model = model.to(device)
        predictor = KronosPredictor(model, tokenizer, max_context=min(req.lookback, int(ids["context"])))
        x_df = df.tail(req.lookback)[["open", "high", "low", "close", "volume", "amount"]].reset_index(drop=True)
        x_timestamp = df.tail(req.lookback)["timestamps"].reset_index(drop=True)
        y_timestamp = _future_timestamps(x_timestamp.iloc[-1], req.pred_len, req.interval)
        pred_df = predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=req.pred_len,
            T=req.temperature,
            top_k=req.top_k,
            top_p=req.top_p,
            sample_count=req.sample_count,
            verbose=False,
        )
        if "close" not in pred_df or pred_df["close"].empty:
            errors.append("Kronos returned no close forecast")
            return None, device, warnings, errors, model_revision, tokenizer_revision, checksum, {}
        latest_close = float(x_df["close"].iloc[-1])
        last_pred = float(pred_df["close"].iloc[-1])
        change = round((last_pred / latest_close - 1.0) * 100.0, 4) if latest_close else None
        prediction_meta = {
            "predicted_close_last": round(last_pred, 6),
            "forecast_start_timestamp": str(pred_df.index[0]) if len(pred_df.index) else None,
            "forecast_end_timestamp": str(pred_df.index[-1]) if len(pred_df.index) else None,
        }
        return change, device, warnings, errors, model_revision, tokenizer_revision, checksum, prediction_meta
    except Exception as exc:  # pragma: no cover
        errors.append(f"Kronos runtime failed: {exc}")
        return None, device, warnings, errors, model_revision, tokenizer_revision, "unknown", {}


def build_result(req: KronosForecastRequest, fetcher: Callable[..., tuple[Any, dict[str, Any]]] = fetch_yahoo_ohlcv) -> tuple[KronosForecastResult, Any | None]:
    start = time.monotonic()
    ids = MODEL_IDS.get(req.model, MODEL_IDS["mini"])
    result = KronosForecastResult(
        symbol=req.symbol,
        analysis_date=req.analysis_date,
        model_name=ids["model"],
        tokenizer_name=ids["tokenizer"],
        model_revision=req.model_revision or str(ids.get("model_revision") or "not-pinned"),
        tokenizer_revision=req.tokenizer_revision or str(ids.get("tokenizer_revision") or "not-pinned"),
        lookback=req.lookback,
        pred_len=req.pred_len,
        seed=req.seed,
        temperature=req.temperature,
        top_k=req.top_k,
        top_p=req.top_p,
        sample_count=req.sample_count,
        data_source=req.data_source,
        data_constraints=infer_data_constraints(req.symbol),
    )
    df = None
    try:
        df, meta = fetcher(req.symbol, range_=req.range_, interval=req.interval)
        result.data_source = meta.get("source") or req.data_source
        result.missing_bars_count = int(meta.get("missing_bars_count") or 0)
        result.amount_missing = bool(meta.get("amount_missing", True))
        result.data_points = int(len(df))
        if len(df):
            result.latest_close = round(float(df["close"].iloc[-1]), 6)
        if len(df) < req.lookback:
            result.warnings.append(f"available bars {len(df)} < lookback {req.lookback}; smoke can run only as degraded evidence")
    except Exception as exc:
        result.status = "unavailable"
        result.usability = "unavailable"
        result.errors.append(f"data fetch failed: {exc}")
        result.runtime_seconds = round(time.monotonic() - start, 3)
        return result, None

    deps = dependency_report()
    missing = [name for name, ok in deps.items() if not ok]
    if missing:
        result.warnings.append("real Kronos runtime not available: missing " + ", ".join(missing))
    if not req.allow_download:
        result.warnings.append("real model download/run disabled by default; pass --allow-download plus --kronos-repo and pinned --revision for true Kronos smoke")
    if req.allow_download and not missing:
        change, device, warnings, errors, model_revision, tokenizer_revision, checksum, prediction_meta = _run_real_kronos(req, df)
        result.device = device
        result.warnings.extend(warnings)
        result.errors.extend(errors)
        result.model_revision = model_revision
        result.tokenizer_revision = tokenizer_revision
        result.checksum = checksum
        if change is not None and not errors:
            result.model_available = True
            result.status = "ok"
            result.usability = "usable"
            result.forecast_change_pct = change
            result.predicted_close_last = prediction_meta.get("predicted_close_last")
            result.forecast_start_timestamp = prediction_meta.get("forecast_start_timestamp")
            result.forecast_end_timestamp = prediction_meta.get("forecast_end_timestamp")
            result.forecast_direction = _direction(change)
            result.confidence = 0.2  # smoke-level only; promotion requires walk-forward validation.
        else:
            result.status = "degraded"
            result.usability = "degraded"
            result.forecast_direction = "uncertain"
            result.confidence = 0.0
    else:
        result.status = "degraded"
        result.usability = "degraded"
        result.forecast_direction = "uncertain"
        result.confidence = 0.0
        result.device = "not-used"

    result.scoring_impact = 0
    result.protected_writeback = False
    result.runtime_seconds = round(time.monotonic() - start, 3)
    return result, df


def render_markdown(result: KronosForecastResult) -> str:
    d = result.to_dict()
    warnings = "\n".join(f"- {w}" for w in result.warnings) or "- none"
    errors = "\n".join(f"- {e}" for e in result.errors) or "- none"
    constraints = "\n".join(f"- {c}" for c in result.data_constraints) or "- none"
    return f"""# Kronos Forecast Challenger Smoke

## Verdict

- Status: `{result.status}`
- Usability: `{result.usability}`
- Symbol: `{result.symbol}`
- Model available: `{result.model_available}`
- Forecast direction: `{result.forecast_direction}`
- Forecast change pct: `{result.forecast_change_pct}`
- Confidence: `{result.confidence}`
- Scoring impact: `{result.scoring_impact}`
- Protected writeback: `{result.protected_writeback}`

## Model / data

- Upstream project: `shiyu-coder/Kronos` / `NeoQuasar` Hugging Face model family
- Model: `{result.model_name}`
- Tokenizer: `{result.tokenizer_name}`
- Model revision: `{result.model_revision}`
- Tokenizer revision: `{result.tokenizer_revision}`
- Checksum: `{result.checksum}`
- Device: `{result.device}`
- Data source: `{result.data_source}`
- Bars: `{result.data_points}`
- Missing bars: `{result.missing_bars_count}`
- Amount missing/proxy: `{result.amount_missing}`
- Latest close: `{result.latest_close}`
- Predicted close last: `{result.predicted_close_last}`
- Forecast window: `{result.forecast_start_timestamp}` → `{result.forecast_end_timestamp}`
- Lookback / pred_len: `{result.lookback}` / `{result.pred_len}`
- Seed / top_k / top_p / sample_count: `{result.seed}` / `{result.top_k}` / `{result.top_p}` / `{result.sample_count}`

## Warnings

{warnings}

## Errors

{errors}

## Data constraints before promotion

{constraints}

## Boundary

This file is sidecar evidence only. It must not update `12_preliminary_deep_review.md`, must not change scoring, and must not write `state/portfolio.md` or `trades/trade-log.md`.
"""


def render_html(result: KronosForecastResult) -> str:
    badge = {"ok": "#16a34a", "degraded": "#d97706", "unavailable": "#dc2626"}.get(result.status, "#64748b")
    rows = [
        ("Status", result.status),
        ("Usability", result.usability),
        ("Symbol", result.symbol),
        ("Model", result.model_name),
        ("Model revision", result.model_revision),
        ("Tokenizer revision", result.tokenizer_revision),
        ("Checksum", result.checksum),
        ("Forecast", f"{result.forecast_direction} / {result.forecast_change_pct}"),
        ("Predicted close last", result.predicted_close_last),
        ("Forecast window", f"{result.forecast_start_timestamp} → {result.forecast_end_timestamp}"),
        ("Confidence", result.confidence),
        ("Scoring impact", result.scoring_impact),
        ("Protected writeback", result.protected_writeback),
        ("Data points", result.data_points),
        ("Missing bars", result.missing_bars_count),
        ("Amount proxy", result.amount_missing),
        ("Seed / top_k / top_p / sample_count", f"{result.seed} / {result.top_k} / {result.top_p} / {result.sample_count}"),
    ]
    row_html = "".join(f"<tr><th>{html.escape(str(k))}</th><td>{html.escape(str(v))}</td></tr>" for k, v in rows)
    warn_html = "".join(f"<li>{html.escape(w)}</li>" for w in result.warnings) or "<li>none</li>"
    err_html = "".join(f"<li>{html.escape(e)}</li>" for e in result.errors) or "<li>none</li>"
    constraints_html = "".join(f"<li>{html.escape(c)}</li>" for c in result.data_constraints) or "<li>none</li>"
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>Kronos Forecast Challenger</title>
<style>body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0f172a;color:#e2e8f0;margin:32px}}.card{{max-width:980px;margin:auto;background:#111827;border:1px solid #334155;border-radius:16px;padding:24px}}.badge{{display:inline-block;background:{badge};color:white;border-radius:999px;padding:6px 12px;font-weight:700}}table{{border-collapse:collapse;width:100%;margin-top:18px}}th,td{{border-bottom:1px solid #334155;text-align:left;padding:10px}}th{{width:220px;color:#93c5fd}}code{{color:#fde68a}}li{{margin:6px 0}}.muted{{color:#94a3b8}}</style></head>
<body><main class=\"card\"><p class=\"badge\">{html.escape(result.status.upper())}</p><h1>Kronos Forecast Challenger Smoke</h1><p class=\"muted\">Sidecar evidence only. No scoring impact, no protected writeback.</p><table>{row_html}</table><h2>Warnings</h2><ul>{warn_html}</ul><h2>Errors</h2><ul>{err_html}</ul><h2>Promotion constraints</h2><ul>{constraints_html}</ul></main></body></html>"""


def write_outputs(result: KronosForecastResult, out: Path) -> KronosForecastResult:
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "17_kronos_forecast.json"
    md_path = out / "17_kronos_forecast.md"
    html_path = out / "17_kronos_forecast.html"
    result.output_files = {"json": str(json_path), "md": str(md_path), "html": str(html_path)}
    json_path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    html_path.write_text(render_html(result), encoding="utf-8")
    return result


def run_forecast(req: KronosForecastRequest, topic: str = "kronos-smoke", fetcher: Callable[..., tuple[Any, dict[str, Any]]] = fetch_yahoo_ohlcv) -> KronosForecastResult:
    result, _ = build_result(req, fetcher=fetcher)
    out = archive_dir(req.analysis_date, topic)
    return write_outputs(result, out)
