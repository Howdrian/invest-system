from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import json
import re
import sys

try:
    from schemas import EvidenceClaim, ExternalAgentEvidence, validate_ticker
except ImportError:  # pragma: no cover - package-style import fallback
    from .schemas import EvidenceClaim, ExternalAgentEvidence, validate_ticker


RATING_RE = re.compile(
    r"(?:\*\*)?(?:Rating|Recommendation|Action)(?:\*\*)?\s*:\s*(?:\*\*)?"
    r"(Buy|Overweight|Hold|Underweight|Sell)(?:\*\*)?",
    re.IGNORECASE,
)
ENTRY_RE = re.compile(r"(?:Entry Price|Entry)\s*(?:\*\*)?\s*:\s*\$?([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
STOP_RE = re.compile(r"(?:Stop Loss|Stop)\s*(?:\*\*)?\s*:\s*\$?([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


SECTION_ALIASES = {
    "market analyst": "market",
    "market analysis": "market",
    "social analyst": "sentiment",
    "social sentiment": "sentiment",
    "sentiment": "sentiment",
    "news analyst": "news",
    "news analysis": "news",
    "fundamentals analyst": "fundamentals",
    "fundamentals analysis": "fundamentals",
    "bull researcher": "bull",
    "bear researcher": "bear",
    "research manager": "research_manager",
    "trader": "trader",
    "trading team plan": "trader",
    "aggressive analyst": "aggressive_risk",
    "conservative analyst": "conservative_risk",
    "neutral analyst": "neutral_risk",
    "portfolio manager": "portfolio_manager",
    "portfolio management decision": "portfolio_manager",
}

CATALYST_KEYWORDS = (
    "catalyst",
    "earnings",
    "guidance",
    "contract",
    "approval",
    "launch",
    "policy",
    "supply",
    "demand",
    "capacity",
)

UNKNOWN_MARKERS = (
    "unknown",
    "not available",
    "no data",
    "unable",
    "cannot verify",
    "missing",
)


def normalize_heading(title: str) -> str | None:
    clean = re.sub(r"^\d+\.\s*", "", title.strip().lower())
    clean = clean.replace("###", "").strip()
    for alias, canonical in SECTION_ALIASES.items():
        if alias in clean:
            return canonical
    return None


def sections_from_markdown(markdown: str) -> dict[str, str]:
    matches = list(HEADING_RE.finditer(markdown))
    sections: dict[str, list[str]] = {}
    if not matches:
        return {"complete_report": markdown.strip()}

    for i, match in enumerate(matches):
        title = match.group(2)
        key = normalize_heading(title)
        if key is None:
            continue
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        content = markdown[start:end].strip()
        if content:
            sections.setdefault(key, []).append(content)

    return {key: "\n\n".join(parts).strip() for key, parts in sections.items()}


def sections_from_state(state: dict[str, Any]) -> dict[str, str]:
    sections: dict[str, str] = {}
    mapping = {
        "market_report": "market",
        "sentiment_report": "sentiment",
        "news_report": "news",
        "fundamentals_report": "fundamentals",
        "investment_plan": "research_manager",
        "trader_investment_plan": "trader",
        "final_trade_decision": "portfolio_manager",
    }
    for state_key, section_key in mapping.items():
        value = state.get(state_key)
        if isinstance(value, str) and value.strip():
            sections[section_key] = value.strip()

    debate = state.get("investment_debate_state") or {}
    if isinstance(debate, dict):
        if debate.get("bull_history"):
            sections["bull"] = str(debate["bull_history"]).strip()
        if debate.get("bear_history"):
            sections["bear"] = str(debate["bear_history"]).strip()

    risk = state.get("risk_debate_state") or {}
    if isinstance(risk, dict):
        risk_mapping = {
            "aggressive_history": "aggressive_risk",
            "conservative_history": "conservative_risk",
            "neutral_history": "neutral_risk",
            "judge_decision": "portfolio_manager",
        }
        for state_key, section_key in risk_mapping.items():
            value = risk.get(state_key)
            if isinstance(value, str) and value.strip():
                sections[section_key] = value.strip()

    return sections


def extract_rating(text: str) -> str | None:
    match = RATING_RE.search(text)
    if not match:
        return None
    return match.group(1).title()


def extract_price(regex: re.Pattern[str], text: str) -> float | None:
    match = regex.search(text)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def candidate_snippets(text: str, limit: int = 4) -> list[str]:
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        if len(line) < 24:
            continue
        if line.startswith("#"):
            continue
        lines.append(line)
    if lines:
        return lines[:limit]

    paragraphs = [p.strip().replace("\n", " ") for p in text.split("\n\n") if len(p.strip()) >= 24]
    return paragraphs[:limit]


def claims_from_section(section: str, text: str, claim_type: str, limit: int = 4) -> list[EvidenceClaim]:
    claims = []
    for snippet in candidate_snippets(text, limit=limit):
        claims.append(
            EvidenceClaim(
                claim=snippet[:500],
                type=claim_type,
                source_section=section,
                evidence=snippet[:500],
            )
        )
    return claims


def catalysts_from_sections(sections: dict[str, str], limit: int = 6) -> list[EvidenceClaim]:
    catalysts: list[EvidenceClaim] = []
    for section, text in sections.items():
        for snippet in candidate_snippets(text, limit=8):
            low = snippet.lower()
            if any(keyword in low for keyword in CATALYST_KEYWORDS):
                catalysts.append(
                    EvidenceClaim(
                        claim=snippet[:500],
                        type="catalyst",
                        source_section=section,
                        evidence=snippet[:500],
                    )
                )
            if len(catalysts) >= limit:
                return catalysts
    return catalysts


def unknowns_from_sections(sections: dict[str, str], limit: int = 10) -> list[str]:
    unknowns: list[str] = []
    for section, text in sections.items():
        for snippet in candidate_snippets(text, limit=12):
            low = snippet.lower()
            if any(marker in low for marker in UNKNOWN_MARKERS):
                unknowns.append(f"{section}: {snippet[:300]}")
            if len(unknowns) >= limit:
                return unknowns
    return unknowns


def build_evidence(ticker: str, analysis_date: str, sections: dict[str, str]) -> ExternalAgentEvidence:
    safe_ticker = validate_ticker(ticker)
    combined = "\n\n".join(sections.values())
    rating = None
    for preferred_section in ("portfolio_manager", "research_manager", "trader"):
        if preferred_section in sections:
            rating = extract_rating(sections[preferred_section])
            if rating:
                break
    if rating is None:
        rating = extract_rating(combined)

    evidence = ExternalAgentEvidence(
        source="tradingagents",
        ticker=safe_ticker,
        analysis_date=analysis_date,
        rating=rating,
        suggested_entry=extract_price(ENTRY_RE, combined),
        suggested_stop=extract_price(STOP_RE, combined),
        raw_sections=sections,
    )

    for section in ("bull", "fundamentals", "market", "research_manager"):
        if section in sections:
            evidence.claims.extend(claims_from_section(section, sections[section], "bull"))

    for section in ("bear", "conservative_risk", "neutral_risk", "aggressive_risk"):
        if section in sections:
            evidence.risks.extend(claims_from_section(section, sections[section], "risk"))

    evidence.catalysts.extend(catalysts_from_sections(sections))
    evidence.unknowns.extend(unknowns_from_sections(sections))
    return evidence


def parse_inputs(ticker: str, analysis_date: str, report: Path | None, state_json: Path | None) -> ExternalAgentEvidence:
    sections: dict[str, str] = {}

    if report:
        markdown = report.read_text(encoding="utf-8")
        sections.update(sections_from_markdown(markdown))

    if state_json:
        state = json.loads(state_json.read_text(encoding="utf-8"))
        if isinstance(state, dict):
            sections.update(sections_from_state(state))

    if not sections:
        raise ValueError("No parseable TradingAgents report or state content found")

    return build_evidence(ticker, analysis_date, sections)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse TradingAgents report into external evidence JSON.")
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--analysis-date", required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--state-json", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    evidence = parse_inputs(args.ticker, args.analysis_date, args.report, args.state_json)
    evidence.write_json(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
