# Macro Review — 2026-06-19

- Status: `DEGRADED`
- Confidence: `LOW_TO_MEDIUM`
- Prediction market: `available`
- Boundary: review-only; no trade execution; no scoring gate bypass.

## 主结论

宏观中性，等待价格和证据共振；VIX neutral: 16.94

## 宏观四维度 / 风险温度

| Dimension | Status | Signal | Evidence |
|---|---|---|---|
| `growth` | `degraded` | `unknown` | GDP/PMI/employment official extensions not yet fully wired in invest-system. |
| `inflation` | `degraded` | `unknown` | CPI/PCE/EIA/FRED extension points pending; use original 投研 source as migration reference. |
| `rates_liquidity` | `available_limited` | `neutral_or_unknown` | 官方宏观源刷新入口已接入；无 key 时只提供降级上下文。 |
| `energy_commodities` | `degraded` | `watch` | WTI/EIA/FRED not fully wired; Polymarket energy scenarios can only be optional hints. |
| `usd_fx` | `missing` | `unknown` | DXY/USD/CNH not wired in v1. |
| `risk_appetite` | `degraded` | `neutral` | VIX neutral: 16.94 |
| `market_heat` | `available` | `watchlist_or_hotspot` | focus_items=26 |

## 6 因子 Regime

- Risk state: `neutral`
- Six-factor status: `DEGRADED`
- Reason: VIX neutral: 16.94
- Boundary: 六因子缺项时只作为宏观降级判断，不冒充满血 Regime。

## 地缘四场景 / Polymarket 融合

| Scenario | Internal | Market | Weight | Fused | Red Team |
|---|---:|---:|---:|---:|---|
| A 管控下降 | 30.0% | - | 0% | 35.0% | `False` |
| B 危机级联 | 40.0% | - | 0% | 35.0% | `False` |
| C 大国冲突 | 20.0% | - | 0% | 15.0% | `False` |
| D 核武尾部 | 10.0% | - | 0% | 10.0% | `False` |

## 对资产/候选池影响

- 维持观察，等待宏观、板块和个股证据共振。
- Polymarket 和宏观只影响候选优先级、风险预算和红队问题，不直接交易。

## Data gaps

- `macro_context_not_refreshed`
- `six_factor_missing:credit_conditions`
- `six_factor_missing:size_factor`
- `six_factor_missing:equity_bond`
- `six_factor_missing:sector_rotation`
