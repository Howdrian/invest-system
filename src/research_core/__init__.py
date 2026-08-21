# -*- coding: utf-8 -*-
"""Pure evidence, semantic validation, and reliability contracts.

This package is intentionally side-effect free: no file IO, network, DB, LLM,
FastAPI, or renderer imports. Runtime pipelines adapt their evidence and claims
into these functions; ReportArtifact remains the only publication contract.
"""

from .contracts import (
    AtomicClaim,
    ClaimStatus,
    ClaimType,
    ClaimValidation,
    EvidenceFact,
    EvidencePool,
    EvidenceType,
    evidence_pool_from_dicts,
)
from .semantic_gate import validate_claim, validate_claim_dicts
from .reliability import (
    build_challenge_verdicts,
    build_research_reliability,
    build_scenario_adjudication,
)

__all__ = [
    "AtomicClaim",
    "ClaimStatus",
    "ClaimType",
    "ClaimValidation",
    "EvidenceFact",
    "EvidencePool",
    "EvidenceType",
    "evidence_pool_from_dicts",
    "validate_claim",
    "validate_claim_dicts",
    "build_research_reliability",
    "build_scenario_adjudication",
    "build_challenge_verdicts",
]
