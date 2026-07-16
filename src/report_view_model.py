"""Reader-facing view helpers for report rendering.

This module is deliberately pure: it maps artifact/source-health values into
reader copy. HTML assembly stays in ``render_report_html.py``.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

STATUS_LABELS = {
    "FULL_REVIEW": "完整复盘",
    "LIMITED_REVIEW": "有限复盘",
    "SCREEN_ONLY": "仅筛选观察",
    "OBSERVE_ONLY": "仅市场观察",
    "BLOCKED": "数据不足",
    "REFRESHED": "已刷新",
    "AVAILABLE": "可用",
    "available": "可用",
    "available_limited": "有限可用",
    "DEGRADED": "降级",
    "degraded": "降级",
    "PARTIAL": "部分可用",
    "partial": "部分可用",
    "missing": "缺失",
    "failed": "失败",
    "empty": "空结果",
    "rate_limited": "限流",
    "permission_limited": "权限不足",
    "not_supported": "暂不支持",
    "fresh": "新鲜",
    "stale": "已变旧",
    "usable": "可用",
    "usable_limited": "有限可用",
    "limited": "有限可用",
    "unavailable": "不可用",
    "unknown": "未知",
}

REGIME_LABELS = {
    "NEUTRAL_WATCH": "中性观察",
    "RISK_OFF": "风险收缩",
    "RISK_ON": "风险偏好",
    "UNKNOWN": "未知",
}

AGENT_ROLE_LABELS = {
    "SourceReviewAgent": "检查今天的数据源是否可信",
    "MacroGeopoliticsAgent": "判断宏观和地缘背景",
    "MacroAgent": "判断宏观和流动性背景",
    "GeoPolicyAgent": "判断地缘、政策、贸易和冲突事件传导",
    "MarketAgent": "复核大盘结构和市场宽度",
    "SectorAgent": "复核行业、风格和热点持续性",
    "MarketStrategyAgent": "把宏观、热度和候选池合成市场策略",
    "CandidateReviewAgent": "解释候选为什么入池或等待",
    "PortfolioReviewAgent": "复核持仓和组合风险",
    "DecisionReportAgent": "给出个股最终读者结论",
    "EvidenceGateAgent": "检查核心结论有没有证据",
    "ScoringAgent": "把证据转成评分和门槛判断",
    "RedBlueAgent": "做多空反证对抗",
    "RedTeamAgent": "专门反驳当前结论",
    "CIOAgent": "汇总成最终投研结论",
}

AGENT_DISPLAY_NAMES = {
    "SourceReviewAgent": "数据源复核",
    "MacroGeopoliticsAgent": "宏观与地缘",
    "MacroAgent": "宏观",
    "GeoPolicyAgent": "地缘政策",
    "MarketAgent": "市场",
    "SectorAgent": "行业/风格",
    "MarketStrategyAgent": "市场策略",
    "CandidateReviewAgent": "候选复核",
    "PortfolioReviewAgent": "持仓复核",
    "DecisionReportAgent": "最终结论",
    "EvidenceGateAgent": "证据复核",
    "ScoringAgent": "评分复核",
    "RedBlueAgent": "多空反证",
    "RedTeamAgent": "红队反证",
    "CIOAgent": "CIO 总结",
}


def reader_status(value: Any) -> str:
    text = str(value or "unknown")
    return STATUS_LABELS.get(text, STATUS_LABELS.get(text.upper(), text))


def reader_regime(value: Any) -> str:
    text = str(value or "UNKNOWN")
    return REGIME_LABELS.get(text.upper(), text)


def macro_reader_copy(macro: Dict[str, Any]) -> Tuple[str, str, str]:
    status = str(macro.get("status") or "").upper()
    gaps = macro.get("data_gaps") or []
    six_factor = macro.get("six_factor_regime") if isinstance(macro.get("six_factor_regime"), dict) else {}
    missing_factors = six_factor.get("missing_factors") or []
    if status in {"REFRESHED", "AVAILABLE"} and not gaps and not missing_factors:
        return (
            "宏观源已刷新，可作为市场背景和风险温度输入；仍不能单独触发个股交易。",
            "宏观可用：允许进入个股证据复核，但交易动作仍看 governed 个股。",
            "继续观察增长、通胀、利率、信用和风险偏好是否同步变化。",
        )
    if status in {"PARTIAL", "DEGRADED"}:
        return (
            "宏观不满血：有可用信号，但仍有因子缺口；只能判断风险温度和候选优先级。",
            "宏观只可背景参考，不是满血 regime。",
            "补齐缺失宏观因子后再提高宏观置信度。",
        )
    return (
        "宏观输入不足；本轮不能形成完整宏观判断。",
        "只保留观察，不提升交易置信度。",
        "先刷新官方宏观源，再重新生成报告。",
    )


def source_health_reader_copy(health: Dict[str, Any]) -> Tuple[str, str, str]:
    usability = str(health.get("usability_verdict") or "").lower()
    trade = str(health.get("trade_review_usability") or "").lower()
    if usability == "usable" and trade == "usable":
        return (
            "核心数据源可用，报告可进入常规投研复核。",
            "数据健康未构成主要阻断；仍需看个股证据。",
            "继续保留 provider ledger 和 evidence ledger 追溯。",
        )
    if trade == "usable_limited" or usability == "degraded":
        return (
            "有可用源，也有降级源；系统只能有限复盘。",
            "可以阅读结论和候选，但不能冒充满血投研。",
            "优先修复 blocking source、限流和关键事实缺口。",
        )
    return (
        "关键源不可用或缺失，报告只能做诊断。",
        "不应输出交易动作。",
        "先恢复核心源，再重新跑 Agent。",
    )


def agent_role_label(agent: str) -> str:
    return AGENT_ROLE_LABELS.get(agent, "解释本模块结论、证据和下一步")


def agent_display_name(agent: str) -> str:
    return AGENT_DISPLAY_NAMES.get(agent, agent.replace("Agent", ""))


def reader_confidence_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "high":
        return "高"
    if text == "medium":
        return "中等"
    if text == "low":
        return "低"
    return str(value or "未标")


def provider_repair_items(provider_matrix: Iterable[Any]) -> List[Dict[str, str]]:
    priority = {
        "auth_missing": 1,
        "failed": 2,
        "empty": 3,
        "not_supported": 4,
        "rate_limited": 5,
        "partial": 6,
    }
    rows: List[Dict[str, str]] = []
    for idx, raw in enumerate(provider_matrix):
        if not isinstance(raw, dict):
            continue
        status = str(raw.get("status") or "partial")
        if status == "success":
            continue
        provider = str(raw.get("provider") or "unknown")
        operation = str(raw.get("operation") or raw.get("domain") or "source")
        if status == "auth_missing":
            label = f"配置 {provider} key"
        elif status == "rate_limited":
            label = f"等待 {provider} 配额恢复或切 fallback"
        elif status == "not_supported":
            label = f"{provider} 当前样例无适配标的"
        elif status == "empty":
            label = f"检查 {provider} 是否无结果"
        else:
            label = f"修复 {provider} 返回"
        rows.append(
            {
                "sort": f"{priority.get(status, 9):02d}-{label}-{idx}",
                "label": label,
                "detail": f"{status} · {operation} · {raw.get('errorType') or 'no_error_type'}",
            }
        )
    rows.sort(key=lambda item: item["sort"])
    return rows


def reader_confidence(score: Any) -> str:
    try:
        value = float(score)
    except (TypeError, ValueError):
        return "可信度未标"
    if value >= 0.85:
        return "高可信"
    if value >= 0.6:
        return "中等可信"
    return "低可信"


def reader_blockers(source_health_v2: Dict[str, Any], evidence_stats: Dict[str, Any], claim_policy: Dict[str, Any]) -> List[str]:
    blockers: List[str] = []
    if claim_policy.get("canActionableAdvice") is False:
        blockers.append("交易建议的证据覆盖有限，需结合触发条件阅读。")
    if claim_policy.get("canPositionSizing") is False:
        blockers.append("仓位区间需结合真实持仓和风险预算复核。")
    missing = evidence_stats.get("missingCriticalFacts")
    if isinstance(missing, int) and missing > 0:
        blockers.append(f"关键证据缺口：{missing}。")
    for reason in source_health_v2.get("blockingReasons") or []:
        text = str(reason)
        if not text:
            continue
        if "auth_missing" in text:
            blockers.append("部分数据源缺少授权配置。")
        elif "rate_limited" in text:
            blockers.append("部分数据源限流。")
        elif "missing" in text:
            blockers.append("部分关键事实缺失。")
        elif "degraded" in text:
            blockers.append("部分数据源降级。")
        elif "agent_reported_data_gap" in text:
            blockers.append("部门复核指出关键数据仍有缺口。")
        elif "no_completed_governed_report" in text:
            blockers.append("本轮没有完成可行动个股深评。")
    return list(dict.fromkeys(blockers))[:6]
