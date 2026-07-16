# -*- coding: utf-8 -*-
"""Pure evidence and atomic-claim contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from hashlib import sha256
from typing import Any, Iterable, List, Mapping, Sequence


class EvidenceType(str, Enum):
    RAW_OBSERVATION = "raw_observation"
    VERIFIED_FACT = "verified_fact"
    DERIVED_FACT = "derived_fact"
    DISCOVERY = "discovery"
    AGENT_OPINION = "agent_opinion"
    SELLSIDE_OPINION = "sellside_opinion"
    FINAL_CLAIM = "final_claim"
    MISSING = "missing"


class ClaimType(str, Enum):
    FACT = "fact"
    INTERPRETATION = "interpretation"
    SCENARIO = "scenario"
    RECOMMENDATION = "recommendation"


class ClaimStatus(str, Enum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    HYPOTHESIS = "hypothesis"
    DISPUTED = "disputed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class EvidenceFact:
    id: str
    fact_type: EvidenceType | str
    subject: str = ""
    value: str = ""
    provider: str = ""
    source_url: str = ""
    raw_path: str = ""
    as_of: str = ""
    event_time: str = ""
    published_at: str = ""
    fetched_at: str = ""
    confidence: str = "medium"
    supports_action: bool = False
    evidence_scope: str = "subject_evidence"
    domain: str = ""
    metric: str = ""
    measurements: Mapping[str, Any] = field(default_factory=dict)
    unit: str = ""
    period_start: str = ""
    period_end: str = ""
    filing_form: str = ""
    fiscal_period: str = ""
    fiscal_year: str = ""
    frame: str = ""

    def normalized_type(self) -> EvidenceType:
        if isinstance(self.fact_type, EvidenceType):
            return self.fact_type
        return EvidenceType(str(self.fact_type))

@dataclass(frozen=True)
class AtomicClaim:
    id: str
    text: str
    claim_type: ClaimType | str = ClaimType.INTERPRETATION
    subject: str = ""
    domain: str = ""
    metric: str = ""
    time_scope: str = ""
    evidence_ids: Sequence[str] = field(default_factory=tuple)
    source_agent: str = ""

    def normalized_type(self) -> ClaimType:
        if isinstance(self.claim_type, ClaimType):
            return self.claim_type
        return ClaimType(str(self.claim_type))


@dataclass(frozen=True)
class ClaimValidation:
    claim_id: str
    status: ClaimStatus | str
    reasons: Sequence[str] = field(default_factory=tuple)
    accepted_evidence_ids: Sequence[str] = field(default_factory=tuple)
    rejected_evidence_ids: Sequence[str] = field(default_factory=tuple)
    safe_text: str = ""

    def normalized_status(self) -> ClaimStatus:
        if isinstance(self.status, ClaimStatus):
            return self.status
        return ClaimStatus(str(self.status))

    @staticmethod
    def stable_id(*, subject: str, fact_type: str, value: str, provider: str = "", source_url: str = "", raw_path: str = "", as_of: str = "") -> str:
        payload = "|".join([subject, fact_type, provider, source_url, raw_path, as_of, value]).strip()
        return "ev:" + sha256(payload.encode("utf-8")).hexdigest()[:20]


@dataclass(frozen=True)
class EvidencePool:
    facts: Sequence[EvidenceFact] = field(default_factory=tuple)


def evidence_pool_from_dicts(items: Iterable[Mapping[str, Any]]) -> EvidencePool:
    facts: List[EvidenceFact] = []
    for item in items:
        fact_type = str(item.get("factType") or item.get("fact_type") or EvidenceType.DISCOVERY.value)
        subject = str(item.get("symbol") or item.get("subject") or "")
        value = str(item.get("value") or item.get("fact") or item.get("summary") or "")
        fact_id = str(item.get("id") or EvidenceFact.stable_id(
            subject=subject,
            fact_type=fact_type,
            value=value,
            provider=str(item.get("provider") or ""),
            source_url=str(item.get("sourceUrl") or item.get("source_url") or ""),
            raw_path=str(item.get("rawPath") or item.get("raw_path") or ""),
            as_of=str(item.get("asOf") or item.get("as_of") or ""),
        ))
        facts.append(EvidenceFact(
            id=fact_id,
            fact_type=fact_type,
            subject=subject,
            value=value,
            provider=str(item.get("provider") or ""),
            source_url=str(item.get("sourceUrl") or item.get("source_url") or ""),
            raw_path=str(item.get("rawPath") or item.get("raw_path") or ""),
            as_of=str(item.get("asOf") or item.get("as_of") or ""),
            event_time=str(item.get("eventTime") or item.get("event_time") or ""),
            published_at=str(item.get("publishedAt") or item.get("published_at") or ""),
            fetched_at=str(item.get("fetchedAt") or item.get("fetched_at") or ""),
            confidence=str(item.get("confidence") or "medium"),
            supports_action=bool(item.get("supportsAction") or item.get("supports_action")),
            evidence_scope=str(item.get("evidenceScope") or item.get("evidence_scope") or "subject_evidence"),
            domain=str(item.get("domain") or ""),
            metric=str(item.get("metric") or item.get("concept") or item.get("series") or ""),
            measurements=dict(item.get("measurements") or item.get("metrics") or {}),
            unit=str(item.get("unit") or ""),
            period_start=str(item.get("periodStart") or item.get("period_start") or item.get("start") or ""),
            period_end=str(item.get("periodEnd") or item.get("period_end") or item.get("end") or ""),
            filing_form=str(item.get("filingForm") or item.get("filing_form") or item.get("form") or ""),
            fiscal_period=str(item.get("fiscalPeriod") or item.get("fiscal_period") or item.get("fp") or ""),
            fiscal_year=str(item.get("fiscalYear") or item.get("fiscal_year") or item.get("fy") or ""),
            frame=str(item.get("frame") or ""),
        ))
    return EvidencePool(tuple(facts))
