# Deep Review Queue

- Cycle dir: `research/archive/2026-06-01-research-cycle`
- Generated: `2026-06-01T13:33:47+00:00`
- Selection: top `6` from candidates with REVIEW / score >= `7.0` / source evidence.
- Lane: `all`.
- Diversification: max `4` candidates per market by default, so A股加权但不挤掉美股/ETF。
- Boundary: 深度重评队列，不是交易建议；交易仍必须通过红蓝对抗与评分门控。

## Queue

| Rank | Symbol | Name | Market | Asset | Lanes | Sector | Verdict | Priority | Base | Evidence quality | Price risk | Next action | Evidence | Review file |
|---:|---|---|---|---|---|---|---|---:|---:|---|---|---|---|---|
| 1 | `600111.SS` | 北方稀土 | A | equity_or_etf | a_share | 稀土 | DEEP_REVIEW_NOW | 23.23 | 15.53 | HIGH_OFFICIAL_EVIDENCE (8.7) | PULLBACK_OR_WEAK_CONFIRM_FIRST | 读原文 + 找止跌/反转确认 | event_candidates:6, gov_policy_items:4, official_extension_points:4 | `research/archive/2026-06-01-research-cycle/deep_reviews/600111.SS.md` |
| 2 | `002466.SZ` | 天齐锂业 | A | commodity_proxy | a_share,commodity | 锂 | DEEP_REVIEW_NOW | 23.23 | 15.53 | HIGH_OFFICIAL_EVIDENCE (11.7) | PULLBACK_OR_WEAK_CONFIRM_FIRST | 读原文 + 找止跌/反转确认 | report_candidates:5, event_candidates:6, gov_policy_items:4, official_extension_points:4 | `research/archive/2026-06-01-research-cycle/deep_reviews/002466.SZ.md` |
| 3 | `002460.SZ` | 赣锋锂业 | A | commodity_proxy | a_share,commodity | 锂 | DEEP_REVIEW_NOW | 23.23 | 15.53 | HIGH_OFFICIAL_EVIDENCE (13.2) | PULLBACK_OR_WEAK_CONFIRM_FIRST | 读原文 + 找止跌/反转确认 | report_triggers:1, report_candidates:5, event_candidates:6, gov_policy_items:4, official_extension_points:4 | `research/archive/2026-06-01-research-cycle/deep_reviews/002460.SZ.md` |
| 4 | `600893.SS` | 航发动力 | A | equity_or_etf | a_share,geopolitics | 军工 | DEEP_REVIEW_NOW | 22.93 | 15.53 | HIGH_OFFICIAL_EVIDENCE (5.3) | PULLBACK_OR_WEAK_CONFIRM_FIRST | 读原文 + 找止跌/反转确认 | event_candidates:6, gov_policy_items:2 | `research/archive/2026-06-01-research-cycle/deep_reviews/600893.SS.md` |
| 5 | `XLK` | Technology Select Sector SPDR | US | equity_or_etf | us | 美股科技 | DEEP_REVIEW_NOW | 20.3 | 13.8 | MEDIUM_MIXED_EVIDENCE (7.8) | NORMAL_RECHECK | 启动完整红蓝重评 | report_triggers:1, report_candidates:5, event_candidates:3 | `research/archive/2026-06-01-research-cycle/deep_reviews/XLK.md` |
| 6 | `SMH` | VanEck Semiconductor ETF | US | equity_or_etf | us | 半导体ETF | DEEP_REVIEW_NOW | 20.1 | 13.8 | MEDIUM_MIXED_EVIDENCE (7.8) | NORMAL_RECHECK | 启动完整红蓝重评 | report_triggers:1, report_candidates:5, event_candidates:6 | `research/archive/2026-06-01-research-cycle/deep_reviews/SMH.md` |

## 解释

- `DEEP_REVIEW_NOW`：证据和分数足够，应该启动完整红蓝重评。
- `DEEP_REVIEW_WAIT_ENTRY`：值得重评，但短线过热或远离均线，优先评估回踩/确认，不追高。
- `DEEP_REVIEW_EVIDENCE_CHECK`：有公告/研报/事件线索，先核原文，再决定是否升级。
- `WATCH_ONLY_RECHECK`：暂时只是候选，继续观察。
- Evidence quality 会区分官方原文/SEC/CNINFO、研报/事件、纯价格热度，防止热榜噪音直接升级。

## 下一步标准动作

1. 逐个打开 `deep_reviews/*.md`。
2. 对 `DEEP_REVIEW_*` 的标的补读原文和最新价格结构。
3. 只有 thesis 改变且评分 ≥ 6.0，才进入红蓝对抗。
