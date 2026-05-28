# External Project Integration Policy

Last reviewed: 2026-05-23

## Decision

The system should use external financial projects, but not replace the local decision system.

- Local truth source: `AGENTS.md`, `skill.md`, `agents/red-team-protocol.md`, `agents/scoring-card.md`.
- Direct integrations are allowed only for data adapters and deterministic calculators.
- AI agents, quant engines, backtest engines and model forecasts stay sidecar until they pass independent validation.

## Integration pattern

```text
invest-brain local authority
  ├─ direct data adapters: OpenBB / AKShare / edgartools / Tradier / Polygon / Alpaca / IBKR
  ├─ direct calculators: QuantLib / py_vollib / Riskfolio / skfolio
  ├─ sidecar challengers: TradingAgents / Kronos / LEAN / Qlib / vectorbt / FinGPT
  ├─ references only: Anthropic financial-services / Optopsy / OptionLab / FinRobot / FinRL / NautilusTrader
  └─ optional paid-provider blueprints: FactSet / S&P Capital IQ / Daloopa / Morningstar / LSEG / Aiera 等
```

## Promotion gates

A sidecar can only be promoted after:

1. source and license review;
2. local adapter smoke;
3. schema validation and source health output;
4. protected writeback audit;
5. no-lookahead validation for backtests/models;
6. costs, slippage and liquidity assumptions documented;
7. forward ledger with enough samples;
8. explicit decision that it still does not replace red-blue review or local scoring.

## Current priorities

1. Build `options-long-only` as a formal lane.
2. Add options data provider probe: Tradier / Polygon / Alpaca / IBKR / Yahoo fallback.
3. Add Anthropic-style coverage / earnings / valuation workbench after deep-review candidate selection, not in the default daily scan.
4. Add external project registry health checks.
5. Add automation profiles so recurring jobs run fixed workflows instead of free-form prompts.
6. Add post-event / post-candidate settlement ledgers for Polymarket, deep-review candidates and options.

## Anthropic financial-services boundary

`anthropics/financial-services` is a high-quality official reference for financial workflow packaging:

- adopt: vertical plugin pattern, bundled agent-plugin pattern, managed-agent cookbook pattern, source citation discipline, untrusted-document guardrails, schema validation, market-researcher / earnings-reviewer / model-builder workflow templates;
- do not adopt: paid MCP dependencies as default blockers, external agent authority, direct score mapping, protected-file writeback, publishing or execution flows.

Detailed adoption note: `docs/anthropic-financial-services-adoption.md`.

See: `config/external-projects-registry.md`.
