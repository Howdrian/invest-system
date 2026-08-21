# -*- coding: utf-8 -*-
"""Deterministic semantic trust boundary for research claims.

The gate never upgrades a claim.  It checks whether cited evidence is the
right kind of evidence for the sentence being written, not merely whether an
identifier exists.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from .contracts import (
    AtomicClaim,
    ClaimStatus,
    ClaimType,
    ClaimValidation,
    EvidenceFact,
    EvidenceType,
    evidence_pool_from_dicts,
)


_CONDITIONAL_MARKERS = ("若", "如果", "可能", "或将", "情景", "一旦")
_YIELD_CURVE_RE = re.compile(r"收益率曲线|(?:10Y|十年期).{0,8}(?:2Y|两年期|3M|三个月).{0,8}(?:倒挂|利差)", re.I)
_YIELD_SPREAD_VALUE_RE = re.compile(r"(T10Y2Y|T10Y3M)\s*=\s*(-?\d+(?:\.\d+)?)", re.I)
_SAHM_RE = re.compile(r"萨姆规则|Sahm", re.I)
_HISTORICAL_RE = re.compile(r"历史.{0,8}(?:低位|高位|分位)|极度.{0,5}(?:低位|高位)|极(?:低|高)(?:水平|位置)|软着陆幻想")
_APPLE_LAWSUIT_RE = re.compile(r"苹果|Apple|AAPL", re.I)
_LAWSUIT_RE = re.compile(r"起诉|诉讼|法院|侵权|商业机密|禁令")
_REDEMPTION_RE = re.compile(r"公募|基金|ETF|机构")
_FLOW_RE = re.compile(r"赎回|申赎|被动减仓|流动性负反馈")
_CAPITAL_FLOW_RE = re.compile(
    r"资金(?:向|流向|流入|流出|加速流向|抱团|撤离)|资金被迫|缺乏增量资金|存量资金轮动|护盘|多头踩踏"
    r"|资金[^。；]{0,24}(?:弃[^。；]{1,16}向[^。；]{1,16}|抱团)"
    r"|市场[^。；]{0,24}弃[^。；]{1,16}向[^。；]{1,16}"
)
_CROSS_MARKET_SCOPE_RE = re.compile(
    r"美股表现强于A股(?:和|与)港股|美股表现强于A股|跨市场(?:间)?未(?:出现|见)系统性共振下跌"
    r"|本轮观察标的中[^\u3002；]{0,80}未出现系统性共振下跌"
    r"|美股(?:盘中)?科技股走强|港股震荡偏弱|跨市场联动性较弱"
    r"|美港股[^。；]{0,20}(?:强势|走强|占优|韧性|强)|美港股[^。；]{0,30}A股"
)
_GLOBAL_TECH_SCOPE_RE = re.compile(
    r"全球科技股[^。；]{0,32}(?:派发|回调|下跌|走强|压力加剧)",
    re.I,
)
_STRONG_CAUSAL_RE = re.compile(r"本质上(?:是|就是)|已经证实|必然由|完全由|纯属|完全支持")
_QUARTER_RE = re.compile(r"单季|本季|季度收入|季度营收|季度净利")
_QUALITATIVE_LEVEL_RE = re.compile(
    r"(?:极其|相对|整体)?(?:平稳|稳定|温和|健康|宽松|紧张|极低|极高)(?:区间|水平|环境|状态)?"
    r"|(?:处于|维持在)[^。；]{0,20}(?:较低水平|较高水平|低位|高位|温和区间)"
    r"|极端分化|良性(?:风格)?轮动|流动性(?:依然|仍然|整体)?充裕|极高(?:的)?成交|高达"
)
_MARKET_INTENSITY_RE = re.compile(r"极端分化|极高(?:水平|成交|成交额|的成交量)|良性(?:风格)?轮动")
_MARKET_BREADTH_LANGUAGE_RE = re.compile(
    r"市场宽度[^。；]{0,16}(?:恶化|改善|修复|走弱|转强)|"
    r"市场宽度[^。；]{0,16}(?:偏向空头|偏向多头|偏空|偏多|空头占优|多头占优)|"
    r"市场宽度[^。；]{0,20}(?:崩溃|坍塌)|"
    r"(?:上涨|下跌)家数[^。；]{0,20}(?:多于|少于|超过|低于|占比)",
    re.I,
)
_VALUATION_LABEL_RE = re.compile(
    r"(?:低估值|高估值|估值(?:偏低|偏高|低位|高位|安全区间|具有吸引力)|估值溢价(?:合理|过高))",
    re.I,
)
_VALUATION_BENCHMARK_LANGUAGE_RE = re.compile(
    r"估值[^。；]{0,24}(?:历史低位|历史高位|历史分位|偏低|偏高|低位|高位|安全边际|具有吸引力)|"
    r"(?:低估值|高估值|低估|高估)",
    re.I,
)
_GROWTH_TREND_RE = re.compile(
    r"(?:营收|收入|净利润|净利|业绩|基本面)[^。；]{0,36}(?:增速放缓|增速加快|加速增长|止跌回暖|低速筑底|扩张动能[^。；]{0,8}(?:承压|增强))",
    re.I,
)
_REPORTING_PERIOD_RE = re.compile(
    r"(?P<year>20\d{2})年(?P<period>一季报|第一季度报告|中报|半年报|半年度报告|三季报|第三季度报告|年报|年度报告)",
    re.I,
)
_CORPORATE_ACTION_PRICE_EFFECT_RE = re.compile(
    r"(?:回购|分红|权益分派)[^。；]{0,48}(?:托底|护盘|提供下行防御|形成下行防御|支撑股价|支撑估值|避险属性|防御属性|机制性(?:抗跌)?支撑)",
    re.I,
)
_DELEVERAGING_RE = re.compile(r"(?:结构性|局部|全市场)?去杠杆|获利回吐阶段|共振杀跌阶段", re.I)
_SESSION_MOVE_RE = re.compile(r"(?:盘前|盘后)[^。；]{0,24}(?:上涨|下跌|涨|跌|走强|走弱|微涨|偏弱|偏强)", re.I)
_ALL_TIME_HIGH_RE = re.compile(r"(?:创|刷新|达到|逼近)[^。；]{0,12}(?:历史新高|历史最高|all[- ]?time high)", re.I)
_CAUSAL_ATTRIBUTION_RE = re.compile(
    r"(?:主要|完全)?受[^。；]{1,36}(?:支撑|推动|驱动|拖累|压制)|"
    r"属于[^。；]{1,28}(?:独立)?基本面驱动|"
    r"因[^。；]{1,28}(?:导致|引发|造成)|"
    r"将直接影响|直接导致|从而传导",
    re.I,
)
_ROE_VALUATION_RE = re.compile(r"ROE[^。；]{0,48}(?:支持|证明)[^。；]{0,32}(?:估值|溢价)", re.I)
_GDP_LEVEL_GROWTH_RE = re.compile(
    r"GDP[^。；]{0,48}(?:万亿美元|万亿|总量|基数)[^。；]{0,48}(?:温和增长|稳健增长|增长态势)",
    re.I,
)
_GDP_LEVEL_STRONG_GROWTH_RE = re.compile(
    r"GDP[^。；]{0,64}(?:历史新高|高位|总量)[^。；]{0,48}(?:强劲增长|增长强劲|增长态势|经济韧性)",
    re.I,
)
_GEO_EVENT_RE = re.compile(r"空袭|袭击|封锁|制裁|冲突|战争|出口限制|限制.{0,8}出口|霍尔木兹|关税|贸易禁令")
_SYMBOL_RE = re.compile(
    r"(?<![A-Z0-9])(?:"
    r"(?i:HK\d{4,5})|"
    r"\d{4,6}\.(?i:T|KS|KQ|TW|TWO|HK|SH|SZ|SS|BJ)|"
    r"\d{6}(?:\.(?i:SH|SZ|SS|BJ))?|"
    r"[A-Z]{2,5}(?:\.[A-Z])?"
    r")(?![A-Z0-9])",
)
_NON_SECURITY_ACRONYMS = {
    "AI", "API", "ASEAN", "BIS", "BOE", "BOJ", "CIO", "CN", "CNINFO",
    "CNY", "CPI", "ECB", "ETF", "EU", "FED", "FOMC", "FRED", "GDP",
    "HK", "HKD", "HKEX", "IMF", "IR", "JPY", "KR", "LLM", "MACD",
    "OFAC", "OPEC", "PB", "PBOC", "PE", "PMI", "PPI", "REIT", "ROE",
    "RSI", "SEC", "SMA", "TW", "UK", "US", "USD", "VIX", "WTI",
}
_VOLUME_EXPANSION_RE = re.compile(r"放量|量能(?:明显)?放大|成交量(?:明显)?放大")
_VOLUME_CONTRACTION_RE = re.compile(r"缩量|量能(?:明显)?萎缩|成交量(?:明显)?萎缩")
_VOLUME_RATIO_RE = re.compile(r"volume_vs_avg20\s*=\s*(-?\d+(?:\.\d+)?)", re.I)
_STRONG_FUNDAMENTAL_RE = re.compile(r"严重恶化|业绩暴雷|极高安全边际|强力支撑|必然下修|不具备?可持续性")
_FUNDAMENTAL_DRIVER_RE = re.compile(r"拨备释放|非经常性损益|低基数|会计调整|一次性收益")
_FUNDAMENTAL_DRIVER_EVIDENCE_RE = re.compile(
    r"拨备|provision|非经常性|non.?recurring|低基数|base effect|会计调整|accounting adjustment|一次性|one.?off",
    re.I,
)
_INSIDER_SALE_RE = re.compile(r"(?:高管|内部人|insider).{0,12}(?:减持|卖出|抛售|sale)|Form\s*4.{0,12}(?:减持|卖出|抛售)", re.I)
_FORM4_TRANSACTION_DETAIL_RE = re.compile(
    r"transaction.?code|code\s*=\s*S|acquired.?disposed|shares?\s*=|amount\s*=|减持股数|卖出股数|交易代码",
    re.I,
)
_TECHNICAL_STRUCTURE_RE = re.compile(r"多头趋势|空头趋势|趋势.{0,4}延续|筑底|突破|破位|支撑位|阻力位|量价结构|反弹结构")
_FALSE_DICHOTOMY_RE = re.compile(
    r"(?:若|如果|一旦).{0,56}(?:没有|无|未见|未找到|未证实|不能证实).{0,56}"
    r"(?:则|就|意味着|可以判定|可判定).{0,80}(?:纯交易|超跌|低吸|买入|加仓)",
    re.I,
)
_PORTFOLIO_OUTCOME_RE = re.compile(r"(?:对冲|拖累|改善|提升|降低).{0,18}(?:组合|持仓)|(?:组合|持仓).{0,18}(?:对冲|拖累|跑赢|改善|提升)")
_SECTOR_PERSISTENCE_RE = re.compile(
    r"(?:行业|板块|风格|医药|白酒|银行|科技|半导体).{0,32}(?:持续占优|持续性|防御持续|趋势延续)"
    r"|(?:持续占优|防御持续|趋势延续).{0,24}(?:行业|板块|风格)",
    re.I,
)
_SYSTEMIC_MARKET_STRESS_RE = re.compile(
    r"系统性(?:走弱|弱势(?:调整)?|破位(?:深调)?|去杠杆|风险收缩|流动性(?:危机|收缩)|抛售|踩踏|深幅调整|深调)"
    r"|全市场(?:流动性(?:锁死|危机|收缩)|无差别补跌)"
    r"|无差别(?:去杠杆|抛售|补跌)",
    re.I,
)
_RANGE_POSITION_MISREAD_RE = re.compile(
    r"(?:range_position_pct\s*=\s*100|100\s*%\s*分位(?:数)?)"
    r"[^。；]{0,40}(?:必然|极易|高概率|一定|回吐|反转)",
    re.I,
)
_SYSTEMIC_UNCERTAINTY_RE = re.compile(
    r"(?:尚|仍)?(?:未|没有)(?:发生|看见|确认|证明)?[^。；]{0,16}系统性"
    r"|(?:无法|不能|不足以)[^。；]{0,20}(?:确认|证明|推导)[^。；]{0,16}系统性",
    re.I,
)
_TECHNICAL_SERIES_MARKERS = (
    "SMA", "EMA", "MACD", "RSI", "BOLL", "ATR", "VOLUME_VS_AVG20",
    "HIGH20", "LOW20", "RETURN_5D", "RETURN_20D", "OHLCV",
)
_MARKET_COUNT_PATTERNS = (
    ("up_count", re.compile(r"(?:上涨|收涨)(?:家数)?[^0-9]{0,8}(\d{2,5})\s*(?:家|只)")),
    ("down_count", re.compile(r"(?:下跌|收跌)(?:家数)?[^0-9]{0,8}(\d{2,5})\s*(?:家|只)")),
    ("limit_up_count", re.compile(r"涨停(?:家数)?[^0-9]{0,8}(\d{1,4})\s*家")),
    ("limit_down_count", re.compile(r"跌停(?:家数)?[^0-9]{0,8}(\d{1,4})\s*家")),
    ("up_count", re.compile(r"(\d{2,5})\s*家(?:个股)?(?:上涨|收涨)")),
    ("down_count", re.compile(r"(\d{2,5})\s*家(?:个股)?(?:下跌|收跌)")),
    ("up_count", re.compile(r"(?:超|逾|约|近)?(\d{2,5})\s*只(?:个股)?(?:上涨|收涨)")),
    ("down_count", re.compile(r"(?:超|逾|约|近)?(\d{2,5})\s*只(?:个股)?(?:下跌|收跌)")),
    ("up_count", re.compile(r"上涨(?:与|和)下跌家数比(?:为)?\s*(\d{2,5})\s*(?:对|比)\s*\d{2,5}")),
    ("down_count", re.compile(r"上涨(?:与|和)下跌家数比(?:为)?\s*\d{2,5}\s*(?:对|比)\s*(\d{2,5})")),
    ("up_count", re.compile(r"(?:上涨|涨)[/／](?:下跌|跌)家数比(?:为|达)?\s*(\d{2,5})\s*[/／:]\s*\d{2,5}")),
    ("down_count", re.compile(r"(?:上涨|涨)[/／](?:下跌|跌)家数比(?:为|达)?\s*\d{2,5}\s*[/／:]\s*(\d{2,5})")),
)
_RETURN_PERIOD_RE = re.compile(
    r"(?<!\d)(\d{1,4})\s*日(?:收益率|回报率|累计涨跌幅)[^。；%]{0,24}?(-?\d+(?:\.\d+)?)\s*%",
    re.I,
)
_MARKET_TURNOVER_RE = re.compile(r"(?:两市|A股|全市场)?成交(?:额|金额)[^0-9]{0,10}(\d+(?:\.\d+)?)\s*(万亿|亿元|亿)")
_MARKET_TURNOVER_PRE_RE = re.compile(
    r"(?:两市|A股|全市场)?\s*(\d+(?:\.\d+)?)\s*(万亿|亿元|亿)[^\u3002；，,]{0,12}成交(?:额|金额)"
)
_FUNDAMENTAL_PERCENT_PATTERNS = (
    ("revenue_yoy_pct", re.compile(r"(?:营业总收入|营业收入|营收).{0,12}?同比.{0,8}?(-?\d+(?:\.\d+)?)\s*%")),
    ("net_profit_yoy_pct", re.compile(r"(?:归母净利润|净利润|净利).{0,12}?同比.{0,8}?(-?\d+(?:\.\d+)?)\s*%")),
    ("net_profit_yoy_pct", re.compile(r"(?:归母净利润|净利润|净利).{0,10}?(?:下滑|下降|减少)\s*(\d+(?:\.\d+)?)\s*%")),
)
_INDEX_PERCENT_PATTERNS = tuple(
    (
        metric,
        re.compile(
            rf"{name}(?:指数)?[^。；，,]{{0,16}}?(暴涨|暴跌|大涨|大跌|上涨|下跌|涨|跌)\s*([+-]?\d+(?:\.\d+)?)\s*%"
        ),
    )
    for metric, name in (
        ("index_sh000001_change_pct", "上证指数"),
        ("index_sz399001_change_pct", "深证成指"),
        ("index_sz399006_change_pct", "创业板指"),
        ("index_sh000688_change_pct", "科创50"),
        ("index_sh000016_change_pct", "上证50"),
        ("index_sh000300_change_pct", "沪深300"),
    )
)
_MEASUREMENT_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\s*=\s*(-?\d+(?:\.\d+)?)")
_MEASUREMENT_ALIASES = {
    "up": "up_count",
    "down": "down_count",
    "flat": "flat_count",
    "limit_up": "limit_up_count",
    "limit_down": "limit_down_count",
    "total_amount": "total_amount_100m_cny",
    "total_turnover": "total_amount_100m_cny",
    "revenue_yoy": "revenue_yoy_pct",
    "net_profit_yoy": "net_profit_yoy_pct",
}

_EVIDENCE_MAX_AGE_DAYS = {
    "price": 5,
    "news_sentiment": 10,
    "filings_events": 90,
    "fundamentals": 190,
    "portfolio": 30,
}


def _has_valuation_benchmark(rows: Sequence[EvidenceFact]) -> bool:
    for row in rows:
        text = f"{row.id} {row.metric} {row.value}".upper()
        if any(token in text for token in ("PEER_VALUATION", "PEER_COMPARISON", "VALUATION_PERCENTILE")):
            return True
        try:
            eligible = float(row.measurements.get("valuation_percentile_eligible") or 0)
        except (TypeError, ValueError):
            eligible = 0
        if eligible >= 1 and (
            "VALUATION" in text
            or any("percentile" in str(key).lower() for key in row.measurements)
        ):
            return True
    return False

_DOMAIN_PATTERNS = (
    ("macro", re.compile(r"利率|通胀|失业|流动性|信用利差|美元|汇率|衰退|GDP|VIX|宏观|收益率曲线", re.I)),
    ("fundamentals", re.compile(r"营收|利润|现金流|估值|PE|PB|ROE|毛利率|财报|基本面", re.I)),
    ("filings_events", re.compile(r"公告|法披|SEC|CNINFO|交易所|诉讼|制裁|禁令|披露", re.I)),
    ("portfolio", re.compile(r"持仓|组合|仓位|暴露|集中度", re.I)),
    ("price", re.compile(r"价格|涨跌|趋势|均线|量价|成交量|突破|破位|指数|市场宽度", re.I)),
    ("news_sentiment", re.compile(r"新闻|舆情|事件|搜索线索|媒体|空袭|封锁|制裁|冲突|战争|出口限制|供应链瓶颈", re.I)),
)


def validate_claim(
    claim: AtomicClaim,
    evidence: Iterable[EvidenceFact],
    *,
    reference_date: date | str | None = None,
) -> ClaimValidation:
    by_id = {row.id: row for row in evidence}
    accepted: List[EvidenceFact] = []
    rejected_ids: List[str] = []
    reasons: List[str] = []
    claim_date = _parse_iso_date(reference_date) or _parse_iso_date(claim.time_scope)

    for evidence_id in claim.evidence_ids:
        if str(evidence_id).startswith("memo:"):
            rejected_ids.append(str(evidence_id))
            continue
        row = by_id.get(str(evidence_id))
        if row is None:
            rejected_ids.append(str(evidence_id))
            continue
        rejection = _evidence_trust_rejection(row, claim_date)
        if rejection:
            rejected_ids.append(row.id)
            reasons.append(rejection)
            continue
        if claim.subject and row.subject and not _subject_matches(claim.subject, row):
            rejected_ids.append(row.id)
            continue
        if claim.domain and row.domain and not _domains_overlap({claim.domain}, {row.domain}):
            rejected_ids.append(row.id)
            continue
        if claim.metric and not _evidence_matches_claim_metric(claim.metric, row):
            rejected_ids.append(row.id)
            continue
        accepted.append(row)

    if not accepted:
        reasons.append("no_direct_relevant_evidence")
        return _result(claim, ClaimStatus.REJECTED, reasons, accepted, rejected_ids)

    inferred_subjects = _extract_security_symbols(claim.text)
    supported_subjects = {
        _canonical_security_symbol(str(row.subject or ""))
        for row in accepted
        if row.subject
    }
    if inferred_subjects and not inferred_subjects <= supported_subjects:
        reasons.append("claim_subject_not_supported_by_cited_evidence")

    inferred_domains = _infer_domains(claim.text)
    if inferred_domains:
        accepted_domains = {str(row.domain or "") for row in accepted if row.domain}
        if accepted_domains and any(not _domains_overlap({domain}, accepted_domains) for domain in inferred_domains):
            reasons.append("claim_domain_not_supported_by_cited_evidence")

    expected_metrics = _metric_tokens(claim.metric)
    if expected_metrics:
        supported_metrics = {
            metric
            for metric in expected_metrics
            if any(
                metric == str(row.metric or "").upper()
                or metric in str(row.value or "").upper()
                for row in accepted
            )
        }
        if expected_metrics - supported_metrics:
            reasons.append("claim_metric_not_fully_supported")

    direct_types = {row.normalized_type() for row in accepted}
    only_discovery = direct_types <= {EvidenceType.DISCOVERY, EvidenceType.AGENT_OPINION, EvidenceType.SELLSIDE_OPINION}
    if only_discovery:
        reasons.append("discovery_or_opinion_only")

    refs_upper = " ".join(row.id.upper() for row in accepted)
    values = " ".join(row.value for row in accepted)
    text = claim.text

    numeric_assertions = _numeric_assertions(text)
    if numeric_assertions:
        cited_measurements = _measurement_values(accepted)
        for metric, claimed_value, mode in numeric_assertions:
            evidence_values = cited_measurements.get(metric, [])
            if not evidence_values:
                if metric.startswith(("up_", "down_", "limit_", "total_amount_")):
                    reasons.append("market_stat_not_supported_by_cited_evidence")
                elif metric.startswith("index_"):
                    reasons.append("index_change_not_supported_by_cited_evidence")
                elif metric.startswith("return_"):
                    reasons.append("return_period_not_supported_by_evidence")
                continue
            if not any(_numeric_assertion_matches(metric, claimed_value, actual, mode) for actual in evidence_values):
                if metric in {"revenue_yoy_pct", "net_profit_yoy_pct"}:
                    reasons.append("fundamental_metric_contradicted_by_evidence")
                elif metric.startswith("index_"):
                    reasons.append("index_change_contradicted_by_evidence")
                elif metric.startswith("return_"):
                    reasons.append("return_period_contradicted_by_evidence")
                else:
                    reasons.append("market_stat_contradicted_by_evidence")

    volume_ratios = _volume_ratios_for_claim(claim, accepted)
    is_forward_scenario = (
        claim.normalized_type() == ClaimType.SCENARIO
        or bool(re.match(r"^\s*(?:若|如果|一旦|当|待|只有)", text))
    )
    if (
        _VOLUME_EXPANSION_RE.search(text)
        and volume_ratios
        and max(volume_ratios) < 1.0
        and not is_forward_scenario
    ):
        reasons.append("volume_expansion_contradicted_by_evidence")
    if (
        _VOLUME_CONTRACTION_RE.search(text)
        and volume_ratios
        and min(volume_ratios) > 1.0
        and not is_forward_scenario
    ):
        reasons.append("volume_contraction_contradicted_by_evidence")

    if _STRONG_FUNDAMENTAL_RE.search(text):
        official_filing_support = any(
            row.normalized_type() == EvidenceType.VERIFIED_FACT
            and (
                str(row.domain or "") == "filings_events"
                or any(token in f"{row.provider} {row.id}".upper() for token in ("SEC", "CNINFO", "SSE", "SZSE", "HKEX", "IR"))
            )
            for row in accepted
        )
        if not official_filing_support:
            reasons.append("strong_fundamental_language_requires_official_filing")

    if _FUNDAMENTAL_DRIVER_RE.search(text):
        driver_support = any(
            row.normalized_type() == EvidenceType.VERIFIED_FACT
            and _FUNDAMENTAL_DRIVER_EVIDENCE_RE.search(f"{row.id} {row.metric} {row.value}")
            for row in accepted
        )
        if not driver_support:
            reasons.append("fundamental_driver_requires_filing_detail")

    reporting_period = _REPORTING_PERIOD_RE.search(text)
    if reporting_period:
        year = reporting_period.group("year")
        period = reporting_period.group("period")
        if period in {"中报", "半年报", "半年度报告"}:
            period_markers = ("中报", "半年报", "半年度报告")
        elif period in {"一季报", "第一季度报告"}:
            period_markers = ("一季报", "第一季度报告")
        elif period in {"三季报", "第三季度报告"}:
            period_markers = ("三季报", "第三季度报告")
        else:
            period_markers = ("年报", "年度报告")
        matching_filing = any(
            row.normalized_type() == EvidenceType.VERIFIED_FACT
            and str(row.domain or "") == "filings_events"
            and year in f"{row.id} {row.value}"
            and any(marker in f"{row.id} {row.value}" for marker in period_markers)
            for row in accepted
        )
        if not matching_filing:
            reasons.append("reporting_period_requires_matching_official_filing")

    if _INSIDER_SALE_RE.search(text):
        form4_rows = [
            row
            for row in accepted
            if row.filing_form.upper() == "4" or "FORM4" in row.id.upper() or "FORM 4" in row.value.upper()
        ]
        if form4_rows and not any(
            _FORM4_TRANSACTION_DETAIL_RE.search(f"{row.id} {row.metric} {row.value}")
            for row in form4_rows
        ):
            reasons.append("form4_sale_requires_transaction_detail")

    if _TECHNICAL_STRUCTURE_RE.search(text):
        technical_structure_support = any(
            any(marker in f"{row.id} {row.metric} {row.value}".upper() for marker in _TECHNICAL_SERIES_MARKERS)
            for row in accepted
        )
        if not technical_structure_support:
            reasons.append("technical_structure_requires_series_evidence")

    if _YIELD_CURVE_RE.search(text) and not any(token in refs_upper for token in ("DGS2", "DGS3MO", "T10Y2Y", "T10Y3M")):
        reasons.append("yield_curve_requires_comparable_treasury_maturities")
    curve_spreads = [
        float(value)
        for row in accepted
        for _metric, value in _YIELD_SPREAD_VALUE_RE.findall(f"{row.id} {row.metric} {row.value}")
    ]
    if curve_spreads:
        resolved_language = any(marker in text for marker in ("解除倒挂", "未倒挂", "结束倒挂", "转正"))
        active_inversion_language = "倒挂" in text and not resolved_language
        if active_inversion_language and all(value >= 0 for value in curve_spreads):
            reasons.append("yield_curve_inversion_contradicted_by_spread")
        if resolved_language and any(value < 0 for value in curve_spreads):
            reasons.append("yield_curve_resolution_contradicted_by_spread")
    else:
        resolved_language = any(marker in text for marker in ("解除倒挂", "结束倒挂", "由负转正"))
    if resolved_language and not any(
        any(token in f"{row.id} {row.metric} {row.value}".upper() for token in ("T10Y2Y:HISTORY", "T10Y3M:HISTORY", "SPREAD_HISTORY", "PRIOR_SPREAD"))
        for row in accepted
    ):
        reasons.append("yield_curve_transition_requires_history")

    if _SAHM_RE.search(text) and not any(token in refs_upper for token in ("SAHMREALTIME", "SAHMCURRENT", "SAHM_RULE", "UNRATE_HISTORY")):
        reasons.append("sahm_rule_requires_official_or_historical_calculation")

    valuation_benchmark_support = _has_valuation_benchmark(accepted)
    if _HISTORICAL_RE.search(text) and not any(token in refs_upper for token in ("HISTORY", "PERCENTILE", "ZSCORE", "TIMESERIES")):
        reasons.append("historical_comparison_requires_distribution_evidence")
    if _VALUATION_BENCHMARK_LANGUAGE_RE.search(text) and not valuation_benchmark_support:
        reasons.append("valuation_label_requires_valuation_evidence")

    if _ALL_TIME_HIGH_RE.search(text) and not any(
        token in f"{row.id} {row.metric} {row.value}".upper()
        for row in accepted
        for token in ("ALL_TIME_HIGH", "ALL-TIME HIGH", "ATH=", "FULL_HISTORY_HIGH")
    ):
        reasons.append("all_time_high_requires_full_history_evidence")

    if _APPLE_LAWSUIT_RE.search(text) and _LAWSUIT_RE.search(text):
        official_lawsuit = any(
            row.normalized_type() == EvidenceType.VERIFIED_FACT
            and (
                row.filing_form.upper() == "8-K"
                or "COURT" in row.id.upper()
                or "RECAP" in row.id.upper()
                or "LAWSUIT" in row.id.upper()
                or "LITIGATION" in row.id.upper()
            )
            for row in accepted
        )
        if not official_lawsuit:
            reasons.append("lawsuit_requires_court_ir_or_relevant_filing")

    if _REDEMPTION_RE.search(text) and _FLOW_RE.search(text):
        flow_supported = any(
            any(token in f"{row.id} {row.metric} {row.value}".upper() for token in ("FUND_FLOW", "ETF_FLOW", "REDEMPTION", "申赎", "赎回"))
            for row in accepted
        )
        if not flow_supported:
            reasons.append("fund_redemption_requires_flow_evidence")

    if _CAPITAL_FLOW_RE.search(text):
        flow_supported = any(
            any(
                token in f"{row.id} {row.metric} {row.value}".upper()
                for token in ("CAPITAL_FLOW", "FUND_FLOW", "MONEY_FLOW", "NET_INFLOW", "资金流", "净流入")
            )
            for row in accepted
        )
        if not flow_supported:
            reasons.append("capital_flow_language_requires_flow_evidence")

    if _FALSE_DICHOTOMY_RE.search(text):
        reasons.append("absence_of_one_cause_does_not_prove_alternative_or_action")

    if _PORTFOLIO_OUTCOME_RE.search(text):
        actual_position_support = any(
            str(row.domain or "") == "portfolio"
            and "watchlist" not in f"{row.id} {row.value}".lower()
            and any(
                marker in f"{row.id} {row.metric} {row.value}".lower()
                for marker in ("position_weight", "holding_quantity", "cost_basis", "持仓数量", "持仓权重", "持仓成本")
            )
            for row in accepted
        )
        if not actual_position_support:
            reasons.append("portfolio_outcome_requires_actual_positions")

    if _SECTOR_PERSISTENCE_RE.search(text):
        persistence_support = any(
            any(
                marker in f"{row.id} {row.metric} {row.value}".upper()
                for marker in (
                    "RETURN_5D",
                    "RETURN_20D",
                    "TIMESERIES",
                    "HISTORY",
                    "CAPITAL_FLOW",
                    "FUND_FLOW",
                    "FUNDAMENTAL",
                    "FILINGS_EVENTS",
                )
            )
            for row in accepted
        )
        if not persistence_support:
            reasons.append("sector_persistence_requires_multi_period_or_driver_evidence")

    if (
        _SYSTEMIC_MARKET_STRESS_RE.search(text)
        and not _SYSTEMIC_UNCERTAINTY_RE.search(text)
        and claim.normalized_type() != ClaimType.SCENARIO
        and not re.match(r"^\s*(?:若|如果|一旦|可能|或将|情景)", text)
    ):
        claim_scope = str(claim.subject or "").strip().lower()
        breadth_support = any(
            (
                str(row.subject or "").lower() == claim_scope
                if claim_scope.startswith("market_")
                else str(row.subject or "").lower().startswith("market")
            )
            and any(
                marker in f"{row.id} {row.metric} {row.value}".upper()
                for marker in ("MARKET_STATS", "UP_COUNT", "DOWN_COUNT", "LIMIT_UP", "LIMIT_DOWN")
            )
            for row in accepted
        )
        independent_stress_support = any(
            any(
                marker in f"{row.id} {row.metric} {row.value}".upper()
                for marker in (
                    "CAPITAL_FLOW",
                    "FUND_FLOW",
                    "ETF_FLOW",
                    "REDEMPTION",
                    "BAMLH0A0HYM2",
                    "CREDIT_SPREAD",
                    "TURNOVER_HISTORY",
                    "MARKET_BREADTH_HISTORY",
                )
            )
            for row in accepted
        )
        if not breadth_support or not independent_stress_support:
            reasons.append("systemic_market_stress_requires_breadth_and_liquidity_evidence")

    if _RANGE_POSITION_MISREAD_RE.search(text):
        reasons.append("range_position_is_not_probability_or_valuation_percentile")

    if _CROSS_MARKET_SCOPE_RE.search(text):
        reasons.append("cross_market_scope_requires_market_benchmarks")
    if (
        _GLOBAL_TECH_SCOPE_RE.search(text)
        and claim.normalized_type() != ClaimType.SCENARIO
        and not re.match(r"^\s*(?:若|如果|一旦|可能|或将|情景)", text)
    ):
        reasons.append("cross_market_scope_requires_market_benchmarks")

    if claim.normalized_type() in {ClaimType.INTERPRETATION, ClaimType.RECOMMENDATION} and _STRONG_CAUSAL_RE.search(text):
        direct_mechanism_support = any(
            any(
                token in f"{row.id} {row.metric} {row.value}".upper()
                for token in ("CAPITAL_FLOW", "FUND_FLOW", "MONEY_FLOW", "NET_INFLOW", "TRANSACTION_DETAIL", "资金流", "净流入")
            )
            for row in accepted
        )
        if not direct_mechanism_support:
            reasons.append("strong_causal_language_requires_direct_mechanism_evidence")

    if claim.normalized_type() in {ClaimType.INTERPRETATION, ClaimType.RECOMMENDATION} and _CAUSAL_ATTRIBUTION_RE.search(text):
        direct_mechanism_support = any(
            any(
                token in f"{row.id} {row.metric} {row.value}".upper()
                for token in (
                    "CAPITAL_FLOW", "FUND_FLOW", "MONEY_FLOW", "NET_INFLOW",
                    "TRANSACTION_DETAIL", "EVENT_STUDY", "MANAGEMENT_GUIDANCE",
                    "资金流", "净流入", "回购金额", "回购数量",
                )
            )
            for row in accepted
        )
        if not direct_mechanism_support:
            reasons.append("causal_attribution_requires_mechanism_evidence")

    if _QUARTER_RE.search(text):
        sec_facts = [row for row in accepted if "SEC_COMPANYFACTS" in row.id.upper()]
        if sec_facts and not all((row.period_start and row.period_end) or row.frame for row in sec_facts):
            reasons.append("quarter_claim_requires_period_metadata")

    if _QUALITATIVE_LEVEL_RE.search(text) and not any(
        token in refs_upper for token in ("HISTORY", "PERCENTILE", "ZSCORE", "THRESHOLD", "TIMESERIES")
    ):
        reasons.append("qualitative_level_requires_benchmark")

    if _MARKET_INTENSITY_RE.search(text):
        market_benchmark_support = any(
            str(row.subject or "").lower() == "market"
            and any(
                token in f"{row.id} {row.metric} {row.value}".upper()
                for token in ("HISTORY", "PERCENTILE", "ZSCORE", "TIMESERIES")
            )
            for row in accepted
        )
        if not market_benchmark_support:
            reasons.append("market_intensity_requires_market_benchmark")

    if (
        _MARKET_BREADTH_LANGUAGE_RE.search(text)
        and claim.normalized_type() != ClaimType.SCENARIO
        and not re.match(r"^\s*(?:若|如果|一旦|当|待|只有)", text)
    ):
        claim_scope = str(claim.subject or "").strip().lower()
        breadth_support = any(
            (
                str(row.subject or "").lower() == claim_scope
                if claim_scope.startswith("market_")
                else str(row.subject or "").lower().startswith("market")
            )
            and any(
                marker in f"{row.id} {row.metric} {row.value}".upper()
                for marker in ("MARKET_STATS", "UP_COUNT", "DOWN_COUNT", "LIMIT_UP", "LIMIT_DOWN")
            )
            for row in accepted
        )
        if not breadth_support:
            reasons.append("market_breadth_language_requires_breadth_evidence")

    if _ROE_VALUATION_RE.search(text):
        if not valuation_benchmark_support:
            reasons.append("roe_alone_cannot_justify_valuation")

    if _VALUATION_LABEL_RE.search(text):
        if not valuation_benchmark_support:
            reasons.append("valuation_label_requires_valuation_evidence")

    if _GROWTH_TREND_RE.search(text):
        growth_trend_support = any(
            any(
                token in f"{row.id} {row.metric} {row.value}".upper()
                for token in (
                    "GROWTH_HISTORY", "MULTI_PERIOD", "PRIOR_PERIOD", "COMPARISON_PERIOD",
                    "DELTA_PREV", "REVENUE_YOY_HISTORY", "NET_PROFIT_YOY_HISTORY",
                )
            )
            for row in accepted
        )
        if not growth_trend_support:
            reasons.append("growth_trend_requires_multi_period_evidence")

    if _CORPORATE_ACTION_PRICE_EFFECT_RE.search(text):
        price_effect_support = any(
            any(
                token in f"{row.id} {row.metric} {row.value}".upper()
                for token in ("EVENT_STUDY", "ABNORMAL_RETURN", "CAPITAL_FLOW", "NET_INFLOW")
            )
            for row in accepted
        )
        if not price_effect_support:
            reasons.append("corporate_action_does_not_prove_price_support")

    if _DELEVERAGING_RE.search(text):
        deleveraging_support = any(
            str(row.subject or "").lower() == "market"
            and any(
                token in f"{row.id} {row.metric} {row.value}".upper()
                for token in (
                    "MARGIN_BALANCE", "FINANCING_BALANCE", "LEVERAGE", "MARKET_STATS",
                    "UP_COUNT", "DOWN_COUNT", "CAPITAL_FLOW", "FUND_FLOW", "TOTAL_AMOUNT",
                )
            )
            for row in accepted
        )
        if not deleveraging_support:
            reasons.append("deleveraging_requires_flow_or_leverage_evidence")

    if _SESSION_MOVE_RE.search(text):
        session_rows = " ".join(f"{row.id} {row.value}" for row in accepted).upper()
        if "SESSION=PREMARKET" in session_rows or "SESSION=POSTMARKET" in session_rows:
            reasons.append("collection_session_does_not_prove_session_price_move")

    if _GDP_LEVEL_GROWTH_RE.search(text) or _GDP_LEVEL_STRONG_GROWTH_RE.search(text):
        gdp_growth_support = any(
            any(
                token in f"{row.id} {row.metric} {row.value}".upper()
                for token in ("GDP_GROWTH", "A191RL1Q225SBEA", "GDPC1_GROWTH", "REAL_GDP_GROWTH")
            )
            for row in accepted
        )
        if not gdp_growth_support:
            reasons.append("gdp_level_cannot_prove_growth_rate")

    if _GEO_EVENT_RE.search(text):
        has_verified_event = any(
            row.normalized_type() == EvidenceType.VERIFIED_FACT
            and str(row.domain or "") in {"filings_events", "news_sentiment"}
            for row in accepted
        )
        if not has_verified_event:
            reasons.append("geopolitical_event_not_officially_verified")

    # A provider-run record only proves that data was returned, never the
    # substantive statement itself.
    if accepted and all(row.id.startswith("provider_run:") or "returned " in row.value.lower() for row in accepted):
        reasons.append("provider_run_is_not_substantive_evidence")

    hard_errors = [reason for reason in reasons if reason != "discovery_or_opinion_only"]
    direct_contradictions = {
        "volume_expansion_contradicted_by_evidence",
        "volume_contraction_contradicted_by_evidence",
        "yield_curve_inversion_contradicted_by_spread",
        "yield_curve_resolution_contradicted_by_spread",
        "market_stat_contradicted_by_evidence",
        "index_change_contradicted_by_evidence",
        "fundamental_metric_contradicted_by_evidence",
        "return_period_contradicted_by_evidence",
        "claim_subject_not_supported_by_cited_evidence",
    }
    unsupported_numeric = {
        "market_stat_not_supported_by_cited_evidence",
        "index_change_not_supported_by_cited_evidence",
        "return_period_not_supported_by_evidence",
    }
    if set(hard_errors) & (direct_contradictions | unsupported_numeric):
        status = ClaimStatus.REJECTED
    elif (
        "yield_curve_requires_comparable_treasury_maturities" in hard_errors
        and claim.normalized_type() != ClaimType.SCENARIO
    ):
        status = ClaimStatus.REJECTED
    elif hard_errors:
        hypothesis_errors = {
            "geopolitical_event_not_officially_verified",
            "claim_domain_not_supported_by_cited_evidence",
            "claim_subject_not_supported_by_cited_evidence",
            "capital_flow_language_requires_flow_evidence",
            "strong_causal_language_requires_direct_mechanism_evidence",
            "qualitative_level_requires_benchmark",
            "strong_fundamental_language_requires_official_filing",
            "fundamental_driver_requires_filing_detail",
            "reporting_period_requires_matching_official_filing",
            "technical_structure_requires_series_evidence",
            "cross_market_scope_requires_market_benchmarks",
            "market_intensity_requires_market_benchmark",
            "market_breadth_language_requires_breadth_evidence",
            "roe_alone_cannot_justify_valuation",
            "valuation_label_requires_valuation_evidence",
            "growth_trend_requires_multi_period_evidence",
            "corporate_action_does_not_prove_price_support",
            "deleveraging_requires_flow_or_leverage_evidence",
            "collection_session_does_not_prove_session_price_move",
            "gdp_level_cannot_prove_growth_rate",
            "absence_of_one_cause_does_not_prove_alternative_or_action",
            "portfolio_outcome_requires_actual_positions",
            "sector_persistence_requires_multi_period_or_driver_evidence",
            "systemic_market_stress_requires_breadth_and_liquidity_evidence",
            "range_position_is_not_probability_or_valuation_percentile",
            "all_time_high_requires_full_history_evidence",
            "causal_attribution_requires_mechanism_evidence",
            "yield_curve_transition_requires_history",
            "return_period_not_supported_by_evidence",
        }
        status = (
            ClaimStatus.HYPOTHESIS
            if claim.normalized_type() in {ClaimType.INTERPRETATION, ClaimType.SCENARIO, ClaimType.RECOMMENDATION}
            or set(hard_errors) <= hypothesis_errors
            else ClaimStatus.REJECTED
        )
    elif claim.normalized_type() == ClaimType.SCENARIO:
        status = ClaimStatus.HYPOTHESIS
    elif only_discovery:
        status = ClaimStatus.HYPOTHESIS
    elif rejected_ids:
        status = ClaimStatus.PARTIAL
    else:
        status = ClaimStatus.SUPPORTED
    return _result(claim, status, reasons, accepted, rejected_ids)


def validate_claim_dicts(
    claims: Sequence[Mapping[str, object]],
    evidence_rows: Sequence[Mapping[str, object]],
    *,
    source_agent: str = "",
    reference_date: date | str | None = None,
) -> List[ClaimValidation]:
    pool = evidence_pool_from_dicts(evidence_rows)
    out: List[ClaimValidation] = []
    for index, row in enumerate(claims):
        text = str(row.get("claim") or row.get("text") or "").strip()
        if not text:
            continue
        claim = AtomicClaim(
            id=str(row.get("claimId") or row.get("claim_id") or f"{source_agent or 'claim'}:{index + 1}"),
            text=text,
            claim_type=str(row.get("claimType") or row.get("claim_type") or _infer_claim_type(text)),
            subject=str(row.get("subject") or ""),
            domain=str(row.get("domain") or ""),
            metric=str(row.get("metric") or ""),
            time_scope=str(row.get("timeScope") or row.get("time_scope") or ""),
            evidence_ids=tuple(str(item) for item in row.get("evidence_ids") or row.get("evidenceIds") or []),
            source_agent=source_agent,
        )
        out.append(validate_claim(
            claim,
            pool.facts,
            reference_date=reference_date,
        ))
    return out


def _evidence_trust_rejection(row: EvidenceFact, reference_date: date | None) -> str:
    """Return the first trust-boundary rejection for a cited evidence row."""

    if str(row.evidence_scope or "subject_evidence") != "subject_evidence":
        return "non_subject_evidence_scope"
    fact_type = row.normalized_type()
    if fact_type == EvidenceType.MISSING:
        return "missing_evidence_cannot_support_claim"
    if fact_type == EvidenceType.VERIFIED_FACT and not (row.source_url or row.raw_path):
        return "verified_fact_missing_source"
    if reference_date is None:
        return ""

    observed = _evidence_observed_date(row)
    if observed is None:
        return "evidence_date_missing"
    if observed > reference_date:
        return "evidence_after_claim_time"
    max_age = _evidence_max_age_days(row)
    if (reference_date - observed).days > max_age:
        return "stale_evidence"
    return ""


def _evidence_observed_date(row: EvidenceFact) -> date | None:
    identity = f"{row.id} {row.metric}".lower()
    historical = (
        "history_comparison" in identity
        or "historical" in identity
        or bool(row.period_start or row.period_end)
    )
    values = (
        (row.fetched_at, row.published_at, row.event_time, row.as_of)
        if historical
        else (row.event_time, row.published_at, row.as_of, row.fetched_at)
    )
    return next((parsed for value in values if (parsed := _parse_iso_date(value))), None)


def _evidence_max_age_days(row: EvidenceFact) -> int:
    domain = str(row.domain or "")
    metric = str(row.metric or row.subject or "").upper()
    if domain == "macro":
        if metric == "GDP":
            return 150
        if metric in {"UNRATE", "CPIAUCSL", "SAHMREALTIME"}:
            return 50
        return 14
    return _EVIDENCE_MAX_AGE_DAYS.get(domain, 30)


def _parse_iso_date(value: object) -> date | None:
    text = str(value or "").strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _result(
    claim: AtomicClaim,
    status: ClaimStatus,
    reasons: Sequence[str],
    accepted: Sequence[EvidenceFact],
    rejected_ids: Sequence[str],
) -> ClaimValidation:
    safe_text = claim.text
    if "strong_fundamental_language_requires_official_filing" in reasons:
        safe_text = _soften_strong_language(safe_text)
    if "fundamental_driver_requires_filing_detail" in reasons:
        safe_text = _soften_fundamental_driver_language(safe_text)
    if "reporting_period_requires_matching_official_filing" in reasons:
        safe_text = _soften_reporting_period_language(safe_text)
    if "form4_sale_requires_transaction_detail" in reasons:
        safe_text = _soften_form4_sale_language(safe_text)
    if "strong_causal_language_requires_direct_mechanism_evidence" in reasons:
        safe_text = _soften_strong_causal_language(safe_text)
    if "capital_flow_language_requires_flow_evidence" in reasons:
        safe_text = _soften_capital_flow_language(safe_text)
    if "cross_market_scope_requires_market_benchmarks" in reasons:
        safe_text = _soften_cross_market_scope(safe_text)
    if "qualitative_level_requires_benchmark" in reasons:
        safe_text = _soften_qualitative_level_language(safe_text)
    if "market_intensity_requires_market_benchmark" in reasons:
        safe_text = _soften_qualitative_level_language(safe_text)
    if "market_breadth_language_requires_breadth_evidence" in reasons:
        safe_text = _soften_market_breadth_language(safe_text)
    if "roe_alone_cannot_justify_valuation" in reasons:
        safe_text = _soften_roe_valuation_language(safe_text)
    if "valuation_label_requires_valuation_evidence" in reasons:
        safe_text = _soften_valuation_label_language(safe_text)
    if "growth_trend_requires_multi_period_evidence" in reasons:
        safe_text = _soften_growth_trend_language(safe_text)
    if "corporate_action_does_not_prove_price_support" in reasons:
        safe_text = _soften_corporate_action_price_effect(safe_text)
    if "deleveraging_requires_flow_or_leverage_evidence" in reasons:
        safe_text = _soften_deleveraging_language(safe_text)
    if "collection_session_does_not_prove_session_price_move" in reasons:
        safe_text = _soften_session_move_language(safe_text)
    if "gdp_level_cannot_prove_growth_rate" in reasons:
        safe_text = _soften_gdp_level_growth_language(safe_text)
    if "yield_curve_transition_requires_history" in reasons:
        safe_text = _soften_yield_curve_transition_language(safe_text)
    if "absence_of_one_cause_does_not_prove_alternative_or_action" in reasons:
        safe_text = "一个原因未被证实，只能削弱该解释；替代原因和交易动作仍需独立证据。"
    if "portfolio_outcome_requires_actual_positions" in reasons:
        safe_text = _soften_empty_portfolio_language(safe_text)
    if "sector_persistence_requires_multi_period_or_driver_evidence" in reasons:
        safe_text = _soften_sector_persistence_language(safe_text)
    if "systemic_market_stress_requires_breadth_and_liquidity_evidence" in reasons:
        safe_text = _soften_systemic_market_stress_language(safe_text)
    if "range_position_is_not_probability_or_valuation_percentile" in reasons:
        safe_text = _soften_range_position_language(safe_text)
    if "all_time_high_requires_full_history_evidence" in reasons:
        safe_text = _soften_all_time_high_language(safe_text)
    if "causal_attribution_requires_mechanism_evidence" in reasons:
        safe_text = _soften_causal_attribution_language(safe_text)
    safe_text = _normalize_reader_reasoning_language(safe_text)
    if status == ClaimStatus.REJECTED:
        safe_text = ""
    return ClaimValidation(
        claim_id=claim.id,
        status=status,
        reasons=tuple(dict.fromkeys(reasons)),
        accepted_evidence_ids=tuple(row.id for row in accepted),
        rejected_evidence_ids=tuple(dict.fromkeys(rejected_ids)),
        safe_text=safe_text,
    )


def _numeric_assertions(text: str) -> List[Tuple[str, float, str]]:
    assertions: List[Tuple[str, float, str]] = []
    for metric, pattern in _MARKET_COUNT_PATTERNS:
        for match in pattern.finditer(text):
            assertions.append((metric, float(match.group(1)), _comparison_mode(text, match.start(), match.end())))
    for match in _MARKET_TURNOVER_RE.finditer(text):
        value = float(match.group(1))
        if match.group(2) == "万亿":
            value *= 10000.0
        assertions.append(("total_amount_100m_cny", value, _comparison_mode(text, match.start(), match.end())))
    for match in _MARKET_TURNOVER_PRE_RE.finditer(text):
        value = float(match.group(1))
        if match.group(2) == "万亿":
            value *= 10000.0
        assertions.append(("total_amount_100m_cny", value, _comparison_mode(text, match.start(), match.end())))
    for metric, pattern in _FUNDAMENTAL_PERCENT_PATTERNS:
        for match in pattern.finditer(text):
            value = float(match.group(1))
            segment = text[max(0, match.start()):match.end()]
            if value > 0 and any(marker in segment for marker in ("下降", "下滑", "减少", "负增长")):
                value = -value
            assertions.append((metric, value, "exact"))
    for metric, pattern in _INDEX_PERCENT_PATTERNS:
        for match in pattern.finditer(text):
            direction = match.group(1)
            value = abs(float(match.group(2)))
            if "跌" in direction:
                value = -value
            assertions.append((metric, value, _comparison_mode(text, match.start(), match.end())))
    for match in _RETURN_PERIOD_RE.finditer(text):
        assertions.append((
            f"return_{match.group(1)}d_pct",
            float(match.group(2)),
            _comparison_mode(text, match.start(), match.end()),
        ))
    return list(dict.fromkeys(assertions))


def _comparison_mode(text: str, start: int, end: int) -> str:
    segment = text[max(0, start - 12):min(len(text), end + 2)]
    if any(marker in segment for marker in ("若", "如果", "一旦", "能否", "重回", "恢复至")):
        return "scenario"
    if any(marker in segment for marker in ("超过", "逾", "至少", "不低于", "以上")):
        return "min"
    if any(marker in segment for marker in ("不足", "少于", "至多", "不超过", "以下")):
        return "max"
    if any(marker in segment for marker in ("约", "近", "大约", "接近")):
        return "approx"
    return "exact"


def _measurement_values(evidence: Sequence[EvidenceFact]) -> Dict[str, List[float]]:
    values: Dict[str, List[float]] = {}
    for row in evidence:
        for key, raw in dict(row.measurements or {}).items():
            try:
                number = float(raw)
            except (TypeError, ValueError):
                continue
            canonical = _MEASUREMENT_ALIASES.get(str(key), str(key))
            values.setdefault(canonical, []).append(number)
        for key, raw in _MEASUREMENT_RE.findall(str(row.value or "")):
            canonical = _MEASUREMENT_ALIASES.get(key, key)
            values.setdefault(canonical, []).append(float(raw))
        text = str(row.value or "")
        for metric, name in (
            ("index_sh000001_change_pct", "上证指数"),
            ("index_sz399001_change_pct", "深证成指"),
            ("index_sz399006_change_pct", "创业板指"),
            ("index_sh000688_change_pct", "科创50"),
            ("index_sh000016_change_pct", "上证50"),
            ("index_sh000300_change_pct", "沪深300"),
        ):
            match = re.search(rf"{name}(?:指数)?[^0-9+\-]{{0,8}}([+\-]?\d+(?:\.\d+)?)\s*%", text)
            if match:
                values.setdefault(metric, []).append(float(match.group(1)))
    return values


def _numeric_assertion_matches(metric: str, claimed: float, actual: float, mode: str) -> bool:
    if mode == "scenario":
        return True
    if mode == "min":
        return actual >= claimed
    if mode == "max":
        return actual <= claimed
    if metric.endswith("_count"):
        tolerance = max(0.5, abs(actual) * (0.05 if mode == "approx" else 0.0))
    elif metric == "total_amount_100m_cny":
        tolerance = max(1.0, abs(actual) * (0.05 if mode == "approx" else 0.02))
    else:
        tolerance = max(0.1, abs(actual) * (0.05 if mode == "approx" else 0.02))
    return abs(claimed - actual) <= tolerance


def _soften_strong_language(text: str) -> str:
    replacements = {
        "严重恶化": "显示明显下滑",
        "业绩暴雷": "业绩进一步下行",
        "极高安全边际": "可能存在安全边际",
        "强力支撑": "提供一定支持",
        "必然下修": "可能下修",
        "不具备可持续性": "可持续性尚待验证",
        "不具可持续性": "可持续性尚待验证",
    }
    out = str(text or "")
    for source, target in replacements.items():
        out = out.replace(source, target)
    return out


def _soften_strong_causal_language(text: str) -> str:
    replacements = {
        "本质上就是": "当前更符合",
        "本质上是": "当前更符合",
        "已经证实": "现有证据更支持",
        "必然由": "更可能由",
        "完全由": "主要可由",
        "纯属": "当前更符合",
        "完全支持": "支持",
    }
    out = str(text or "")
    for source, target in replacements.items():
        out = out.replace(source, target)
    return out


def _soften_qualitative_level_language(text: str) -> str:
    """Remove unsupported intensity while preserving the analyst's direction."""

    out = str(text or "")
    replacements = {
        "极端分化": "明显分化",
        "良性风格轮动": "结构性风格轮动",
        "良性轮动": "结构性轮动",
        "流动性依然充裕": "暂未见全市场流动性收缩",
        "流动性仍然充裕": "暂未见全市场流动性收缩",
        "市场整体流动性充裕": "暂未见全市场流动性收缩",
        "极高的成交量": "活跃的成交量",
        "极高成交额": "活跃成交额",
        "健康的结构性分化": "结构性分化",
        "健康的结构性调整": "结构性调整",
        "市场宽度良好": "上涨家数占优",
        "两市量能充沛": "两市成交活跃",
        "极高的资本回报率": "该 ROE 数值",
        "极高水平": "当前水平",
        "较低水平": "当前水平",
        "较高水平": "当前水平",
        "整体稳定": "当前未见明显恶化",
    }
    for source, target in replacements.items():
        out = out.replace(source, target)
    out = re.sub(r"(\d+(?:\.\d+)?\s*(?:万亿|亿元|亿))极高水平", r"\1，成交保持活跃", out)
    out = re.sub(r"成交(?:额|量)?处于极高水平", "成交保持活跃", out)
    out = re.sub(r"处于\s*(-?\d+(?:\.\d+)?)%?\s*的低位", r"为\1%", out)
    out = re.sub(r"处于\s*(-?\d+(?:\.\d+)?)\s*的温和区间", r"为\1", out)
    out = re.sub(r"维持在\s*(-?\d+(?:\.\d+)?)%?\s*的低位", r"为\1%", out)
    out = out.replace("高达", "为")
    return out


def _soften_roe_valuation_language(text: str) -> str:
    return re.sub(
        r"(ROE\s*(?:为|达|约为)?\s*-?\d+(?:\.\d+)?%)[^。；]{0,40}(?:支持|证明)[^。；]{0,32}(?:估值|溢价)[^。；]*",
        r"\1；该指标可能受权益基数影响，不能单独证明估值溢价合理",
        str(text or ""),
        flags=re.I,
    )


def _soften_valuation_label_language(text: str) -> str:
    out = str(text or "")
    replacements = {
        "低估值安全区间": "估值水平仍待补充指标确认",
        "高估值安全区间": "估值水平仍待补充指标确认",
        "低估值下": "估值水平待确认时",
        "高估值下": "估值水平待确认时",
        "低估值": "估值水平待确认的",
        "高估值": "估值水平待确认的",
        "估值偏低": "估值水平待确认",
        "估值偏高": "估值水平待确认",
        "估值具有吸引力": "估值吸引力仍待可比指标确认",
    }
    for source, target in replacements.items():
        out = out.replace(source, target)
    return out


def _soften_growth_trend_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(r"增速放缓至", "本期同比增速为", out)
    out = re.sub(r"增速(?:明显)?放缓", "本期增速已披露；是否放缓需多期数据确认", out)
    out = re.sub(r"增速(?:明显)?加快|加速增长", "本期保持增长；是否加速需多期数据确认", out)
    out = out.replace("止跌回暖迹象", "本期数据改善迹象；是否回暖需多期数据确认")
    out = out.replace("止跌回暖", "本期数据改善；是否回暖需多期数据确认")
    out = out.replace("低速筑底特征", "当前增速较低；是否筑底需多期数据确认")
    out = out.replace("低速筑底", "当前增速较低；是否筑底需多期数据确认")
    out = re.sub(r"扩张动能(?:明显)?承压", "当前增速较低；后续趋势需多期数据确认", out)
    out = re.sub(r"扩张动能(?:明显)?增强", "本期保持增长；后续趋势需多期数据确认", out)
    return out


def _soften_reporting_period_language(text: str) -> str:
    out = str(text or "")
    return re.sub(
        r"[^。；]*20\d{2}年(?:一季报|第一季度报告|中报|半年报|半年度报告|三季报|第三季度报告|年报|年度报告)[^。；]*",
        "涉及特定财报期次的判断须以匹配期次的官方财报核对",
        out,
    )


def _soften_corporate_action_price_effect(text: str) -> str:
    out = str(text or "")
    out = re.sub(
        r"(?:持续)?(?:股份)?回购[^。；]{0,24}(?:提供|形成)[^。；]{0,12}(?:下行)?防御",
        "回购事项已披露，但不能单独证明股价下行空间",
        out,
    )
    out = re.sub(r"(?:回购|分红|权益分派)[^。；]{0,20}(?:托底|护盘|支撑股价|支撑估值)", "相关公司行动已披露，但其价格影响仍待验证", out)
    out = re.sub(r"(?:回购|分红|权益分派)[^。；]{0,40}机制性(?:抗跌)?支撑", "相关公司行动已披露，但其价格影响仍待验证", out)
    out = re.sub(r"(?:回购|分红|权益分派)[^。；]{0,20}(?:具备|提供|形成)(?:较强)?(?:避险|防御)属性", "相关公司行动已披露，但不能单独证明防御属性", out)
    return out


def _soften_deleveraging_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(r"(?:结构性|局部|全市场)?去杠杆", "主要指数深度调整", out)
    out = out.replace("高位题材获利回吐阶段", "高位题材回撤，具体驱动仍待资金与持仓数据确认")
    out = out.replace("共振杀跌阶段", "同步回撤阶段；是否由去杠杆驱动仍待资金与杠杆数据确认")
    return out


def _soften_session_move_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(r"A股观察标的(?:在)?盘前(?:走势|表现)?偏弱", "A股观察标的上一完整交易日表现分化", out)
    out = re.sub(r"A股观察标的盘前", "A股观察标的上一完整交易日", out)
    out = re.sub(r"(600519|000001|贵州茅台|平安银行)([^。；]{0,20})盘前", r"\1\2上一完整交易日", out)
    out = re.sub(r"AAPL[^。；]{0,28}盘后继续上涨", lambda m: m.group(0).replace("盘后继续上涨", "最新行情快照上涨"), out)
    out = re.sub(r"(?:盘后|盘前)(?=[^。；]{0,20}(?:上涨|下跌|涨|跌|走强|走弱|微涨|偏弱|偏强))", "最新行情快照", out)
    return out


def _soften_gdp_level_growth_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(
        r"(?:结合)?[^。；]{0,48}GDP[^。；]{0,64}(?:万亿美元|万亿|历史新高|高位|总量|基数)[^。；]{0,48}(?:温和增长|稳健增长|强劲增长|增长强劲|增长态势|经济韧性)[^。；]*",
        "GDP总量本身不能证明增长速度；现有指标需结合实际增长率、就业与信用数据判断",
        out,
        flags=re.I,
    )
    return out


def _soften_yield_curve_transition_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(
        r"收益率曲线(?:已|已经)?(?:解除倒挂|结束倒挂|由负转正)",
        "当前期限利差为正；是否已结束倒挂需结合历史利差确认",
        out,
    )
    return out


def _soften_empty_portfolio_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(r"(?:已|能够|可以)?对冲(?:了)?(?:部分)?(?:组合|持仓)[^。；]*", "观察池呈现不同风格暴露；未接入真实持仓，不能判断组合对冲效果", out)
    out = re.sub(r"(?:拖累|改善|提升)(?:了)?(?:组合|持仓)[^。；]*", "未接入真实持仓，不能判断对组合收益的实际影响", out)
    out = re.sub(r"(?:组合|持仓)(?:跑赢|得到改善|获得提升)[^。；]*", "未接入真实持仓，不能判断组合收益变化", out)
    return out


def _soften_sector_persistence_language(text: str) -> str:
    out = str(text or "")
    out = out.replace("具备更强防御持续性", "当日防御相对占优，持续性待多日或驱动证据确认")
    out = out.replace("防御持续性更强", "当日防御相对占优，持续性待多日或驱动证据确认")
    out = out.replace("持续占优", "当日相对占优，持续性待验证")
    out = re.sub(r"趋势延续", "当日趋势较强，后续延续需确认", out)
    return out


def _soften_systemic_market_stress_language(text: str) -> str:
    """Keep the directional call while removing an unproved systemic label."""

    source = str(text or "").strip()
    if not source:
        return ""
    if "A股" in source:
        return (
            "A股主要指数显示风险偏好收缩；现有指数证据支持市场转弱，"
            "但尚不足以确认系统性去杠杆，需结合市场宽度、资金流或信用压力复核。"
        )
    softened = source
    for old, new in {
        "系统性去杠杆": "去杠杆风险",
        "系统性走弱": "市场转弱",
        "系统性风险收缩": "风险偏好收缩",
        "系统性流动性危机": "流动性压力",
        "系统性流动性收缩": "流动性压力",
        "系统性抛售": "集中抛售风险",
        "系统性踩踏": "集中回撤风险",
        "系统性深幅调整": "主要指数深度调整",
        "系统性深调": "主要指数深度调整",
        "无差别补跌": "普遍承压风险",
        "无差别去杠杆": "去杠杆风险",
        "无差别抛售": "集中抛售风险",
    }.items():
        softened = softened.replace(old, new)
    return (
        softened.rstrip("。；")
        + "；现有证据不足以确认系统性压力，需结合市场宽度、流动性或信用证据复核。"
    )


def _soften_market_breadth_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(
        r"市场宽度[^。；]{0,16}(?:恶化|改善|修复|走弱|转强)",
        "市场宽度仍待有效数据确认",
        out,
    )
    out = re.sub(
        r"市场宽度[^。；]{0,16}(?:偏向空头|偏向多头|偏空|偏多|空头占优|多头占优)",
        "市场宽度仍待有效数据确认",
        out,
    )
    out = re.sub(
        r"市场宽度[^。；]{0,20}(?:未(?:发生|出现))?(?:崩溃|坍塌)",
        "市场宽度仍待有效数据确认",
        out,
    )
    out = re.sub(
        r"(?:上涨|下跌)家数[^。；]{0,20}(?:多于|少于|超过|低于|占比)[^。；]*",
        "市场宽度仍待有效数据确认",
        out,
    )
    return out


def _soften_all_time_high_language(text: str) -> str:
    return _ALL_TIME_HIGH_RE.sub("处于本轮可见区间高位", str(text or ""))


def _soften_causal_attribution_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(
        r"主要受([^。；]{1,30})支撑",
        r"同期存在\1；二者因果仍待验证",
        out,
    )
    out = re.sub(
        r"受([^。；]{1,30})拖累",
        r"与\1同期走弱；因果仍待验证",
        out,
    )
    out = re.sub(
        r"属于[^。；]{0,20}(?:独立)?基本面驱动",
        "更接近个股自身走势；具体驱动仍待验证",
        out,
    )
    return out


def _soften_range_position_language(text: str) -> str:
    """Treat a range position as a location, never as a probability."""

    out = re.sub(
        r"(?:range_position_pct\s*=\s*100|100\s*%\s*分位(?:数)?)"
        r"[^。；]{0,40}(?:必然|极易|高概率|一定)?(?:触发)?(?:获利)?回吐",
        "位于本轮价格区间上沿；若量价转弱，回撤风险将上升",
        str(text or ""),
        flags=re.I,
    )
    return out.replace("100%分位数", "本轮价格区间上沿").replace("100%分位", "本轮价格区间上沿")


def _normalize_reader_reasoning_language(text: str) -> str:
    """Fix deterministic wording errors without suppressing the conclusion."""

    out = _normalize_subject_currency_units(str(text or ""))
    out = re.sub(
        r"前序部门关于[“\"]防御板块价格表现相对抗跌；是否属于主动资金抱团仍待资金流与市场宽度验证、"
        r"跨市场联动减弱[”\"]的基准判断存在严重的[‘']单股污染[’']与[‘']时效错配[’']",
        "前序部门把少数防御样本的相对抗跌解释为资金抱团，并据此判断跨市场联动减弱；"
        "该结论存在单股污染与时效错配",
        out,
    )
    out = re.sub(
        r"(?:但由于估值与位置高企，)?极易受到本轮 AAPL 与腾讯面临高位回踩风险(?:压力)?的回踩扰动",
        "AAPL 与腾讯面临高位回踩风险",
        out,
    )
    out = re.sub(
        r"(?:但由于估值与位置高企，)?极易受到(?:本轮)?科技观察样本面临高位回踩风险(?:压力)?的回踩扰动",
        "科技观察样本面临高位回踩风险",
        out,
    )
    out = out.replace("全市场流动性并未收缩", "当日宽度与成交暂未显示全市场流动性收缩")
    out = re.sub(
        r"萨姆规则(?:实时)?指标\s*[（(]?(?:SAHMREALTIME)?[）)]?\s*(?:仅为|为)?\s*-?\d+(?:\.\d+)?%?[^。；]{0,24}(?:显示|表明)美国衰退风险极低",
        "萨姆规则指标尚未触发衰退信号",
        out,
        flags=re.I,
    )
    out = re.sub(
        r"宏观基本面[（(](萨姆规则指标尚未触发衰退信号)[）)]?",
        r"\1",
        out,
    )
    out = re.sub(
        r"若(科创50(?:指数)?)无量跌破(\d+(?:\.\d+)?)点(?:整数关口)?(?:，且跌停家数继续扩大)?，?则确立多头踩踏升级",
        r"若\1放量跌破\2点且市场宽度同步恶化，则去杠杆压力升级",
        out,
    )
    out = out.replace(
        "若无量跌破，则确立多头踩踏升级",
        "若放量跌破且市场宽度同步恶化，则去杠杆压力升级",
    )
    out = out.replace("市场宽度同步恶化，导致市场宽度迅速恶化", "市场宽度同步恶化")
    out = re.sub(
        r"(科创50(?:指数)?)明日无量跌破(\d+(?:\.\d+)?)点(?:整数关口)?，且跌停家数继续扩大",
        r"\1明日放量跌破\2点且市场宽度同步恶化",
        out,
    )
    out = out.replace(
        "若缩量则确立调仓结束、市场进入防御阴跌阶段",
        "若成交额持续下降且上涨家数同步收缩，则市场转弱概率上升",
    )
    return out


def _normalize_subject_currency_units(text: str) -> str:
    source = str(text or "")

    def _last_match(pattern: str, end: int) -> int:
        matches = list(re.finditer(pattern, source[:end], re.I))
        return matches[-1].start() if matches else -1

    def _replace(match: re.Match[str]) -> str:
        end = match.start()
        positions = {
            "usd": _last_match(r"AAPL|Apple|苹果", end),
            "hkd": _last_match(r"HK\d{4,5}|腾讯控股", end),
            "cny": _last_match(r"(?<!HK)(?<![A-Z0-9])\d{6}(?![A-Z0-9])|贵州茅台|平安银行", end),
        }
        market = max(positions, key=positions.get)
        if positions[market] < 0:
            return match.group(0)
        suffix = {"usd": "美元", "hkd": "港元", "cny": "元"}[market]
        return f"{match.group(1)}{suffix}"

    return re.sub(r"(\d+(?:\.\d+)?)(?:港元|美元|元)", _replace, source)


def _soften_capital_flow_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(
        r"关于[“\"]资金向([^”\"]{1,32}?)抱团、([^”\"]+)[”\"]",
        r"关于“\1价格相对抗跌、\2”的判断（主动资金抱团尚未被资金流证实）",
        out,
    )
    out = out.replace("在缺乏增量资金环境下的", "的")
    out = out.replace("缺乏增量资金环境下的", "")
    out = out.replace("高位科技股在结构性多头踩踏", "高位科技股的结构性多头踩踏")
    out = out.replace("结构性多头踩踏与获利回吐", "集中回撤与获利回吐")
    out = out.replace("结构性多头踩踏", "集中回撤")
    out = out.replace("发挥护盘作用", "对冲了部分指数跌幅")
    out = out.replace("大金融与消费权重护盘", "大金融与消费权重相对占优")
    out = out.replace("大盘股护盘", "大盘股相对占优")
    out = out.replace("护盘资金力竭", "权重板块转弱")
    out = out.replace("护盘企稳节奏", "相对强势节奏")
    out = out.replace("存量资金轮动", "板块价格轮动")
    out = re.sub(
        r"资金(?:主动)?向([^\u3002；，,]{1,48})(?:进行)?(?:良性|结构性)?轮动",
        r"价格表现呈现\1相对占优",
        out,
    )
    out = re.sub(
        r"资金向([^。；]{1,40}?)抱团(?:(?:的)?特征(?:明显)?)?",
        r"\1价格表现相对抗跌；是否属于主动资金抱团仍待资金流与市场宽度验证",
        out,
    )
    out = re.sub(
        r"(?:资金|市场)(?:呈现|表现出)?(?:显著的|明显的)?[“\"]?弃([^、，。；”\"]{1,16})[、，]向([^，。；”\"]{1,16})[”\"]?(?:去杠杆)?特征",
        r"价格表现呈现\2相对抗跌、\1相对承压；是否由主动资金迁移驱动仍待资金流验证",
        out,
    )
    out = re.sub(r"资金流入([^\u3002；，,]{1,40})迹象明确", r"\1价格表现相对占优", out)
    return out


def _soften_cross_market_scope(text: str) -> str:
    out = str(text or "")
    out = re.sub(r"跨市场对比显示美股表现强于A股(?:和|与)港股", "本轮观察标的中，AAPL 走势相对较强", out)
    out = re.sub(r"美股表现强于A股(?:和|与)港股", "本轮观察标的中 AAPL 走势相对较强", out)
    out = re.sub(r"美股表现强于A股", "本轮观察标的中 AAPL 走势相对较强", out)
    out = re.sub(r"跨市场(?:间)?未(?:出现|见)系统性共振下跌", "本轮跨市场观察标的未同步下跌", out)
    out = re.sub(r"美股(?:盘中)?科技股走强", "本轮美股样本 AAPL 走强", out)
    out = out.replace("港股震荡偏弱", "本轮港股样本腾讯震荡偏弱")
    out = out.replace("跨市场联动性较弱", "样本间未同向波动")
    out = re.sub(r"美港股[^。；]{0,20}(?:强势|走强|占优|韧性|强)", "港美股观察样本相对较强", out)
    out = re.sub(
        r"极易受到全球科技股[^。；]{0,32}(?:派发|回调|下跌|走强|压力加剧)(?:的)?回踩扰动",
        "AAPL 与腾讯面临高位回踩风险",
        out,
    )
    out = re.sub(
        r"(?:当前)?全球科技股[^。；]{0,32}(?:派发|回调|下跌|走强|压力加剧)",
        "本轮科技观察样本面临高位回踩风险",
        out,
    )
    out = out.replace("，未出现系统性共振下跌", "；本轮跨市场观察标的未同步下跌")
    out = re.sub(
        r"本轮观察标的中，?\s*AAPL\s*走势相对较强，未出现系统性共振下跌",
        "本轮观察标的中，AAPL 走势相对较强；本轮跨市场观察标的未同步下跌",
        out,
    )
    return out


def _soften_fundamental_driver_language(text: str) -> str:
    out = str(text or "")
    out = out.replace("极大概率源于", "可能受到")
    out = out.replace("大概率源于", "可能受到")
    out = out.replace("主要来自", "可能受到")
    out = out.replace("可能与", "可能受到")
    out = re.sub(r"可能受到([^，。；]{1,48})([，。；])", r"可能受到\1影响\2", out)
    return out


def _soften_form4_sale_language(text: str) -> str:
    out = str(text or "")
    out = re.sub(r"高管近期存在\s*Form\s*4\s*减持申报", "高管近期存在 Form 4 申报，交易性质待核对", out, flags=re.I)
    out = re.sub(r"Form\s*4\s*减持申报", "Form 4 申报（交易性质待核对）", out, flags=re.I)
    out = re.sub(r"高管近期(?:持续)?减持", "高管近期 Form 4 申报的交易性质待核对", out)
    return out


def _volume_ratios_for_claim(claim: AtomicClaim, accepted: Sequence[EvidenceFact]) -> List[float]:
    """Return only ratios belonging to the security discussed by the claim.

    A downstream CIO sentence can cite evidence for many markets.  A low-volume
    HK stock must not invalidate an aggregate A-share turnover scenario.
    """

    rows_with_ratio = [
        row
        for row in accepted
        if _VOLUME_RATIO_RE.search(str(row.value or ""))
    ]
    if not rows_with_ratio:
        return []

    target_subjects: set[str] = set()
    claim_subject = str(claim.subject or "").strip().upper()
    aggregate_subjects = {"MARKET", "MACRO", "DAILY", "GLOBAL", "PORTFOLIO"}
    if claim_subject and claim_subject not in aggregate_subjects:
        target_subjects.add(_canonical_security_symbol(claim_subject))
    target_subjects.update(_extract_security_symbols(claim.text))
    for row in rows_with_ratio:
        subject = _canonical_security_symbol(str(row.subject or ""))
        if subject and re.search(rf"(?<![A-Z0-9]){re.escape(subject)}(?![A-Z0-9])", claim.text, re.I):
            target_subjects.add(subject)

    aggregate_text = bool(re.search(r"两市|全市场|市场成交|大盘成交|指数成交", claim.text))
    if (claim_subject in aggregate_subjects or aggregate_text) and not target_subjects:
        return []

    if target_subjects:
        relevant = [row for row in rows_with_ratio if _canonical_security_symbol(str(row.subject or "")) in target_subjects]
    else:
        unique_subjects = {str(row.subject or "").strip().upper() for row in rows_with_ratio if row.subject}
        relevant = rows_with_ratio if len(unique_subjects) == 1 else []

    return [
        float(match)
        for row in relevant
        for match in _VOLUME_RATIO_RE.findall(str(row.value or ""))
    ]


def _infer_claim_type(text: str) -> str:
    if any(marker in text for marker in _CONDITIONAL_MARKERS):
        return ClaimType.SCENARIO.value
    if re.search(r"建议|加仓|减仓|买入|卖出|不做|观察", text):
        return ClaimType.RECOMMENDATION.value
    if re.search(r"=|为\d|达到\d|下跌\d|上涨\d|披露|公告", text):
        return ClaimType.FACT.value
    return ClaimType.INTERPRETATION.value


def _infer_domains(text: str) -> set[str]:
    return {domain for domain, pattern in _DOMAIN_PATTERNS if pattern.search(text)}


def _domains_overlap(expected: set[str], actual: set[str]) -> bool:
    aliases = {
        "fundamentals": {"fundamentals", "filings_events"},
        "filings_events": {"filings_events", "news_sentiment"},
        "news_sentiment": {"news_sentiment", "filings_events"},
        "price": {"price", "market"},
        "portfolio": {"portfolio", "price"},
        "macro": {"macro"},
    }
    return any(actual & aliases.get(domain, {domain}) for domain in expected)


def _subject_matches(claim_subject: str, row: EvidenceFact) -> bool:
    """Match concrete symbols strictly and aggregate research scopes by domain.

    Department prompts use subjects such as ``macro`` and ``market`` for an
    aggregate claim.  Rejecting a FRED series because its concrete subject is
    ``DGS10`` makes valid macro analysis impossible.  Concrete stock symbols
    remain exact matches.
    """

    expected = _canonical_security_symbol(str(claim_subject or ""))
    actual = _canonical_security_symbol(str(row.subject or ""))
    if not expected or not actual or expected == actual:
        return True
    aggregate_domains = {
        "DAILY": {"macro", "price", "fundamentals", "filings_events", "news_sentiment", "portfolio"},
        "MACRO": {"macro"},
        "MARKET": {"price", "market", "news_sentiment"},
        "SECTOR": {"price", "market", "news_sentiment"},
        "PORTFOLIO": {"portfolio", "price", "fundamentals"},
    }
    allowed = aggregate_domains.get(expected)
    return bool(allowed and str(row.domain or "") in allowed)


def _canonical_security_symbol(value: str) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("HK") and not text.startswith("HK."):
        digits = text[2:]
        if digits.isdigit() and 1 <= len(digits) <= 5:
            return f"HK{digits.zfill(5)}"
    for prefix in ("SH.", "SZ.", "BJ.", "SH", "SZ", "BJ"):
        if text.startswith(prefix):
            digits = text[len(prefix):]
            if digits.isdigit() and len(digits) in (5, 6):
                return digits
    if "." in text:
        base, suffix = text.rsplit(".", 1)
        if suffix == "HK" and base.isdigit() and 1 <= len(base) <= 5:
            return f"HK{base.zfill(5)}"
        if suffix in {"SH", "SZ", "SS", "BJ"} and base.isdigit():
            return base
        if base in {"SH", "SZ", "SS", "BJ"} and suffix.isdigit():
            return suffix
    return text


def _extract_security_symbols(text: str) -> set[str]:
    symbols: set[str] = set()
    for raw in _SYMBOL_RE.findall(str(text or "")):
        upper = str(raw or "").strip().upper()
        if upper in _NON_SECURITY_ACRONYMS:
            continue
        symbols.add(_canonical_security_symbol(upper))
    return symbols


def _metric_tokens(value: str) -> set[str]:
    return {
        item.strip().upper()
        for item in re.split(r"[,，/|;；]+", str(value or ""))
        if item.strip()
    }


def _evidence_matches_claim_metric(claim_metric: str, row: EvidenceFact) -> bool:
    expected = _metric_tokens(claim_metric)
    if not expected:
        return True
    row_metric = str(row.metric or "").strip().upper()
    value = str(row.value or "").upper()
    return (row_metric in expected if row_metric else False) or any(metric in value for metric in expected)
