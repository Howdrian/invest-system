from __future__ import annotations

from typing import Iterable

try:
    from schemas import PredictionMarketSignal, SignalRun
except ImportError:  # pragma: no cover
    from .schemas import PredictionMarketSignal, SignalRun


def pct(value: float | None) -> str:
    if value is None:
        return "未知"
    return f"{value * 100:.1f}%"


def money(value: float | None) -> str:
    if value is None:
        return "未知"
    return f"${value:,.0f}"


def render_signal_row(signal: PredictionMarketSignal) -> str:
    return (
        f"| {signal.question} | {pct(signal.yes_probability)} | "
        f"{pct(signal.orderbook.spread)} | {money(signal.volume_24h)} | "
        f"{money(signal.liquidity)} | {signal.quality_score:.1f} | "
        f"{signal.quality_bucket} | {signal.recommended_weight:.0%} |"
    )


def top_signals(signals: Iterable[PredictionMarketSignal], limit: int = 20) -> list[PredictionMarketSignal]:
    return sorted(
        signals,
        key=lambda s: (s.quality_score, s.volume_24h, s.liquidity),
        reverse=True,
    )[:limit]


def render_markdown(run: SignalRun, limit: int = 20) -> str:
    signals = top_signals(run.signals, limit=limit)
    rows = "\n".join(render_signal_row(signal) for signal in signals) or "| 无 | - | - | - | - | - | - | - |"
    warnings = "\n".join(f"- {item}" for item in run.warnings) if run.warnings else "- 无"
    rejected = "\n".join(
        f"- {item.get('question') or item.get('event_title')}: {item.get('reason')}" for item in run.rejected[:20]
    ) or "- 无"

    return f"""# Prediction Market Signal

日期：{run.analysis_date}  
生成时间：{run.generated_at}  
主题：`{run.topic}`  
关键词：{', '.join(run.keywords)}

## 结论口径

这是外部预测市场信号，不是交易建议，也不是事实本身。它只能用于校准事件概率、触发红蓝对抗和补充 catalyst clarity；不能单独触发买卖，不能单独让本地评分跨过 6.0。

## 高质量候选市场

| 市场 | YES 概率 | 价差 | 24h 成交 | 流动性 | 质量分 | 桶 | 融合权重上限 |
|---|---:|---:|---:|---:|---:|---|---:|
{rows}

## 使用规则

1. 高质量市场：可作为外部概率校准，初始权重不超过 25%-30%。
2. 中质量市场：只低权重参考，通常 10%-15%。
3. 低质量市场：只观察情绪，不进入概率融合。
4. 如果市场概率和内部判断差异大，触发红队复核，不直接改交易动作。
5. 如果概率快速变化且成交放大，同时相关资产未同步反应，标记为潜在提前信号。

## 被过滤/降权样例

{rejected}

## Warnings

{warnings}

## 数据来源

- Gamma API: market/event discovery
- CLOB API: bid/ask/orderbook
- Data API: recent trades
"""
