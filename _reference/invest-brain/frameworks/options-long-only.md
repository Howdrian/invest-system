# Long-only Options Framework

> Scope: first version for US-listed options only. This framework supports **buying** options as a limited-risk expression of an already-valid thesis. It does not support short option legs.

## Hard boundary

Allowed:

- Long Call
- Long Put
- Protective Put

Not allowed in v1:

- Naked short call / put
- Credit spread / debit spread with short leg
- Iron condor / butterfly / calendar with short leg
- Wheel
- Covered call
- Collar
- 0DTE lottery trades
- Any automatic order placement

Every output is a candidate for review, not a trade instruction.

## When options may be scanned

Options are scanned only after the main research system finds a valid underlying candidate.

Required preconditions:

1. Underlying is in the deep-review queue or explicitly requested by the user.
2. There is a direction thesis: bullish, bearish, or protective hedge.
3. There is a time window: event, earnings, policy, macro release, product launch, regulatory decision, or clear technical/fundamental setup.
4. Option chain data is available with at least bid/ask, expiration, strike, volume/open interest. Greeks/IV are required for full confidence.
5. The candidate passes liquidity and premium-risk filters.

## Default contract selection

| Dimension | Default rule |
|---|---|
| DTE | 45-90 days preferred; 30-120 allowed for review |
| Delta | 0.35-0.65 preferred for directional trades |
| Spread | `(ask-bid)/mid <= 10%`; tighter preferred |
| Open interest | >= 500 preferred |
| Volume | >= 100 preferred |
| IV | Reject absurd/stale IV; high IV requires explicit event-move justification |
| Position risk | single premium loss <= 0.25%-1% account; total long-options premium <= 3%-5% account |

## Output buckets

| Bucket | Meaning |
|---|---|
| `OPTIONS_CANDIDATE_REVIEW` | Contract passes basic data/liquidity/time filters; can enter red-blue review. |
| `OPTIONS_WATCH_DATA_INCOMPLETE` | Underlying thesis may be valid but option chain lacks Greeks/IV or liquidity is marginal. |
| `OPTIONS_BLOCKED` | Do not consider now: no usable chain, wrong market, no catalyst, spread too wide, no liquidity, over-hot chase risk, or no long-only fit. |

## Exit rules for later paper/live use

- Premium down 40%-50%: stop or mandatory re-review.
- Premium up 50%-100%: take partial profit or recover principal.
- 21-30 days before expiry with thesis unfulfilled: exit or roll after fresh review.
- Event trade after catalyst: exit quickly unless new thesis exists.

## Scoring boundary

`options_candidate_score` is a contract-quality and review-priority score only. It is **not** the local 0-10 trade score in `agents/scoring-card.md`.

A real trade still requires:

1. underlying thesis review,
2. option-chain validation,
3. red-blue challenge,
4. local 0-10 scoring-card gate,
5. position sizing,
6. explicit user approval.
