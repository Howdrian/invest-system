from __future__ import annotations

import math


def clamp_probability(p: float, eps: float = 1e-6) -> float:
    return min(1.0 - eps, max(eps, float(p)))


def logit(p: float) -> float:
    p = clamp_probability(p)
    return math.log(p / (1.0 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def linear_fusion(p_internal: float, p_market: float, weight: float) -> float:
    w = min(0.30, max(0.0, float(weight)))
    return (1.0 - w) * clamp_probability(p_internal) + w * clamp_probability(p_market)


def log_odds_fusion(p_internal: float, p_market: float, weight: float) -> float:
    w = min(0.30, max(0.0, float(weight)))
    return sigmoid((1.0 - w) * logit(p_internal) + w * logit(p_market))


def explain_fusion(p_internal: float, p_market: float, weight: float, method: str = "log_odds") -> dict[str, float | str]:
    if method == "linear":
        fused = linear_fusion(p_internal, p_market, weight)
    elif method == "log_odds":
        fused = log_odds_fusion(p_internal, p_market, weight)
    else:
        raise ValueError("method must be linear or log_odds")
    return {
        "method": method,
        "p_internal": round(clamp_probability(p_internal), 6),
        "p_market": round(clamp_probability(p_market), 6),
        "weight": round(min(0.30, max(0.0, float(weight))), 6),
        "p_final": round(fused, 6),
    }
