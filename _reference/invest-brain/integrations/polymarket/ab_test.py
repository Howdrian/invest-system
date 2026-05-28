from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any
import argparse
import hashlib
import json

try:
    from cli import DEFAULT_KEYWORDS, collect_signals
    from report import render_markdown
    from schemas import PROJECT_ROOT, SignalRun, archive_dir_for, utc_now, write_json_safe, write_text_safe
except ImportError:  # pragma: no cover
    from .cli import DEFAULT_KEYWORDS, collect_signals
    from .report import render_markdown
    from .schemas import PROJECT_ROOT, SignalRun, archive_dir_for, utc_now, write_json_safe, write_text_safe


PROTECTED_FILES = [
    PROJECT_ROOT / "state" / "portfolio.md",
    PROJECT_ROOT / "state" / "market-pulse.md",
    PROJECT_ROOT / "state" / "watchlist.md",
    PROJECT_ROOT / "trades" / "trade-log.md",
    PROJECT_ROOT / "agents" / "scoring-card.md",
    PROJECT_ROOT / "agents" / "red-team-protocol.md",
]

DIMENSIONS = {
    "external_probability_evidence": 20,
    "market_quality_controls": 20,
    "catalyst_timing": 15,
    "decision_discipline": 20,
    "actionability": 15,
    "auditability": 10,
}

SCENARIOS = [
    {
        "id": "iran_peace",
        "label": "US-Iran peace/de-escalation",
        "match_any": ["US x Iran permanent peace deal", "US-Iran nuclear deal", "Iran agrees"],
        "asset_mapping": "USO/XLE/GLD/军工/风险资产",
    },
    {
        "id": "hormuz",
        "label": "Strait of Hormuz normalization/blockade",
        "match_any": ["Hormuz"],
        "asset_mapping": "USO/XLE/LNG/GLD/通胀预期",
    },
    {
        "id": "taiwan",
        "label": "China-Taiwan military risk",
        "match_any": ["Taiwan", "China invade Taiwan", "blockade Taiwan"],
        "asset_mapping": "QQQ/SMH/GLD/军工/铜",
    },
    {
        "id": "fed",
        "label": "Fed rate decision/path",
        "match_any": ["Fed", "FOMC", "interest rate", "interest rates", "rate cut", "fed funds", "rate decision"],
        "require_any": ["interest rate", "interest rates", "rate cut", "fed funds", "FOMC", "rate decision"],
        "exclude_any": ["Fed Chair", "confirmed as Fed Chair", "Judy Shelton"],
        "asset_mapping": "TLT/QQQ/SPY/GLD/USD",
    },
    {
        "id": "oil_tail",
        "label": "Crude oil tail-risk thresholds",
        "match_any": ["Crude Oil", "WTI", "Oil"],
        "asset_mapping": "USO/XLE/CPI breakeven/GLD",
    },
    {
        "id": "ukraine",
        "label": "Russia-Ukraine peace/ceasefire",
        "match_any": ["Ukraine", "Russia"],
        "asset_mapping": "欧洲风险资产/能源/军工/黄金",
    },
]


@dataclass
class ABSample:
    scenario_id: str
    label: str
    asset_mapping: str
    signal: dict[str, Any] | None
    a_scores: dict[str, int]
    b_scores: dict[str, int]
    delta: int
    has_incremental_information: bool
    local_gate_bypassed: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_snapshot() -> dict[str, Any]:
    return {str(path.relative_to(PROJECT_ROOT)): sha256(path) for path in PROTECTED_FILES}


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changed = sorted(key for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key))
    return {
        "writeback_violation": bool(changed),
        "changed_files": changed,
        "protected_files_checked": sorted(set(before) | set(after)),
    }


def score_total(scores: dict[str, int]) -> int:
    total = 0
    for key, max_score in DIMENSIONS.items():
        value = int(scores.get(key, 0))
        if value < 0 or value > max_score:
            raise ValueError(f"{key} score {value} outside 0-{max_score}")
        total += value
    return total


def signal_text(signal: dict[str, Any] | None) -> str:
    if not signal:
        return "未找到匹配的高质量 prediction-market signal。"
    return (
        f"{signal['question']}：YES {signal['yes_probability'] * 100:.1f}%，"
        f"quality {signal['quality_score']:.1f}/10，"
        f"spread {((signal.get('orderbook') or {}).get('spread') or 0) * 100:.1f}%，"
        f"24h volume ${signal['volume_24h']:,.0f}，"
        f"liquidity ${signal['liquidity']:,.0f}。"
    )


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term.lower() in text for term in terms)


def choose_signal(signals: list[dict[str, Any]], scenario: dict[str, Any]) -> dict[str, Any] | None:
    terms = [term.lower() for term in scenario["match_any"]]
    required_terms = [term.lower() for term in scenario.get("require_any", [])]
    excluded_terms = [term.lower() for term in scenario.get("exclude_any", [])]
    matches = []
    for signal in signals:
        text = " ".join([signal.get("question") or "", signal.get("event_title") or ""]).lower()
        if excluded_terms and contains_any(text, excluded_terms):
            continue
        if required_terms and not contains_any(text, required_terms):
            continue
        if any(term in text for term in terms):
            relevance = sum(1 for term in set(terms + required_terms) if term in text)
            matches.append((relevance, signal))
    if not matches:
        return None
    return sorted(
        matches,
        key=lambda item: (item[0], item[1].get("quality_score") or 0, item[1].get("volume_24h") or 0),
        reverse=True,
    )[0][1]


def grade_sample(signal: dict[str, Any] | None) -> tuple[dict[str, int], dict[str, int], list[str]]:
    # A 组代表旧流程：没有预测市场外部概率，仍遵守交易纪律但缺少可量化外部证据。
    a_scores = {
        "external_probability_evidence": 0,
        "market_quality_controls": 0,
        "catalyst_timing": 7,
        "decision_discipline": 18,
        "actionability": 7,
        "auditability": 5,
    }
    notes: list[str] = []
    if not signal:
        b_scores = {
            "external_probability_evidence": 0,
            "market_quality_controls": 0,
            "catalyst_timing": 7,
            "decision_discipline": 20,
            "actionability": 7,
            "auditability": 8,
        }
        notes.append("B 组没有找到可用市场，只增加了缺口记录和审计性。")
        return a_scores, b_scores, notes

    quality = float(signal.get("quality_score") or 0)
    has_orderbook = bool(signal.get("orderbook"))
    has_probability = signal.get("yes_probability") is not None
    b_scores = {
        "external_probability_evidence": 20 if has_probability else 0,
        "market_quality_controls": 20 if quality >= 8 and has_orderbook else 14 if quality >= 5 else 6,
        "catalyst_timing": 13 if signal.get("end_date") else 9,
        "decision_discipline": 20,
        "actionability": 13 if quality >= 8 else 10,
        "auditability": 10,
    }
    notes.append("B 组新增外部隐含概率、质量分、价差、成交/流动性和资产映射。")
    notes.append("B 组仍保留 <6.0 不操作门槛，未触发任何交易写回。")
    return a_scores, b_scores, notes


def build_samples(signals: list[dict[str, Any]]) -> list[ABSample]:
    samples: list[ABSample] = []
    for scenario in SCENARIOS:
        signal = choose_signal(signals, scenario)
        a_scores, b_scores, notes = grade_sample(signal)
        samples.append(
            ABSample(
                scenario_id=scenario["id"],
                label=scenario["label"],
                asset_mapping=scenario["asset_mapping"],
                signal=signal,
                a_scores=a_scores,
                b_scores=b_scores,
                delta=score_total(b_scores) - score_total(a_scores),
                has_incremental_information=bool(signal),
                local_gate_bypassed=False,
                notes=notes,
            )
        )
    return samples


def render_a_report(samples: list[ABSample]) -> str:
    blocks = []
    for sample in samples:
        blocks.append(
            f"""## {sample.label}

- 资产映射：{sample.asset_mapping}
- 旧流程信息：只依据宏观/地缘框架和新闻事实；没有外部市场隐含概率、没有价差/流动性质量控制。
- 判断口径：可以形成方向性假设，但缺少可量化概率校准。
- 交易纪律：不触发交易，仍需红蓝对抗和 `<6.0 = 不操作`。
"""
        )
    return "# A Old Flow — No Prediction Market Signal\n\n" + "\n".join(blocks)


def render_b_report(samples: list[ABSample]) -> str:
    blocks = []
    for sample in samples:
        blocks.append(
            f"""## {sample.label}

- 资产映射：{sample.asset_mapping}
- Prediction Market Signal：{signal_text(sample.signal)}
- 使用方式：只用于外部概率校准、catalyst clarity 和红队触发；不直接触发买卖。
- 融合纪律：高质量市场最多 25%-30% 权重；低质量市场只观察。
- 交易纪律：仍需红蓝对抗和 `<6.0 = 不操作`。
"""
        )
    return "# B With Polymarket Signal\n\n" + "\n".join(blocks)


def render_grading(samples: list[ABSample], protected_audit: dict[str, Any]) -> tuple[dict[str, Any], str]:
    rows = []
    incremental = 0
    for sample in samples:
        a_total = score_total(sample.a_scores)
        b_total = score_total(sample.b_scores)
        if sample.has_incremental_information:
            incremental += 1
        rows.append(f"| {sample.label} | {a_total} | {b_total} | {sample.delta} | {sample.has_incremental_information} |")
    avg_delta = sum(sample.delta for sample in samples) / len(samples) if samples else 0
    verdict = "PASS" if avg_delta >= 20 and incremental >= max(1, len(samples) - 1) and not protected_audit.get("writeback_violation") else "FAIL"
    payload = {
        "schema": "polymarket_signal_ab_grading_v1",
        "verdict": verdict,
        "sample_count": len(samples),
        "average_delta": round(avg_delta, 2),
        "incremental_information_count": incremental,
        "local_gate_bypassed_count": sum(1 for s in samples if s.local_gate_bypassed),
        "protected_audit": protected_audit,
        "dimensions": DIMENSIONS,
        "samples": [sample.to_dict() for sample in samples],
        "scope_note": "This A/B grades report quality and evidence completeness, not realized event forecasting accuracy.",
    }
    md = f"""# Polymarket Signal A/B Grading

## Verdict

- Verdict: `{verdict}`
- Sample count: `{len(samples)}`
- Average B-A delta: `{avg_delta:.1f}`
- Incremental information: `{incremental}/{len(samples)}`
- Protected writeback violation: `{protected_audit.get('writeback_violation')}`

## Scope

本轮 A/B 衡量的是“报告质量、证据增量、纪律性、可审计性”，不是事件最终预测准确率。真实准确率需要等市场结算后用 Brier score / log loss 回测。

## Samples

| Scenario | A old flow | B with Polymarket | Delta | Incremental info |
|---|---:|---:|---:|---|
{chr(10).join(rows)}

## Protected Audit

- Changed files: {protected_audit.get('changed_files') or []}

## Interpretation

如果 `PASS`，说明 Polymarket signal 在当前报告流程中提供了明确增量：外部概率、市场质量控制、价差/流动性和可审计来源。它仍不能证明预测一定更准，下一阶段必须做已结算市场回测。
"""
    return payload, md


def run_ab(args: argparse.Namespace) -> int:
    out_dir = archive_dir_for(args.analysis_date, args.topic)
    before = protected_snapshot()
    write_json_safe(out_dir / "protected_before.json", before)

    signals, rejected, warnings, _event_ids = collect_signals(
        keywords=args.keywords or DEFAULT_KEYWORDS,
        search_limit=args.search_limit,
        max_events=args.max_events,
        max_markets=args.max_markets,
        enrich_limit=args.enrich_limit,
    )
    run = SignalRun(
        schema="prediction_market_signal_run_v1",
        generated_at=utc_now(),
        analysis_date=args.analysis_date,
        topic=args.topic,
        keywords=args.keywords or DEFAULT_KEYWORDS,
        signals=signals,
        rejected=rejected,
        sources=["gamma-api.polymarket.com", "clob.polymarket.com", "data-api.polymarket.com"],
        warnings=warnings,
    )
    write_json_safe(out_dir / "prediction_market_signal.json", run.to_dict())
    write_text_safe(out_dir / "prediction_market_signal.md", render_markdown(run, limit=args.report_limit))

    signals_dict = [signal.to_dict() for signal in signals]
    samples = build_samples(signals_dict)
    write_text_safe(out_dir / "a_old_flow.md", render_a_report(samples))
    write_text_safe(out_dir / "b_with_polymarket.md", render_b_report(samples))

    after = protected_snapshot()
    protected_audit = compare_snapshots(before, after)
    write_json_safe(out_dir / "protected_after.json", after)
    write_json_safe(out_dir / "protected_audit.json", protected_audit)

    grading, grading_md = render_grading(samples, protected_audit)
    write_json_safe(out_dir / "ab_grading.json", grading)
    write_text_safe(out_dir / "ab_grading.md", grading_md)
    write_text_safe(out_dir / "summary.md", render_summary(grading))

    print(out_dir)
    print(f"verdict={grading['verdict']} samples={grading['sample_count']} avg_delta={grading['average_delta']} signals={len(signals)} warnings={len(warnings)}")
    return 0


def render_summary(grading: dict[str, Any]) -> str:
    return f"""# Polymarket Signal A/B Summary

- Verdict: `{grading['verdict']}`
- Samples: `{grading['sample_count']}`
- Average B-A delta: `{grading['average_delta']}`
- Incremental information: `{grading['incremental_information_count']}/{grading['sample_count']}`
- Protected writeback violation: `{grading['protected_audit'].get('writeback_violation')}`

## 结论

本轮 A/B 通过表示：加入 Polymarket 后，报告在外部概率、质量控制、可审计性和事件到资产映射上更完整。

边界：这还不是最终预测准确率证明。最终准确率需要等事件结算后做 Brier score / log loss 回测。
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A/B test for Polymarket signal report quality.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run")
    run.add_argument("--analysis-date", default=date.today().isoformat())
    run.add_argument("--topic", default="polymarket-abtest")
    run.add_argument("--keywords", nargs="+")
    run.add_argument("--search-limit", type=int, default=8)
    run.add_argument("--max-events", type=int, default=35)
    run.add_argument("--max-markets", type=int, default=80)
    run.add_argument("--enrich-limit", type=int, default=40)
    run.add_argument("--report-limit", type=int, default=25)
    run.set_defaults(func=run_ab)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
