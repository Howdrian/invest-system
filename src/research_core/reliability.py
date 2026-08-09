# -*- coding: utf-8 -*-
"""Reader-facing reliability and scenario adjudication.

This module is deliberately pure: it consumes department memo dictionaries and
returns a compact product contract.  Source availability and conclusion
reliability are separate concepts; a provider being reachable never upgrades a
research claim.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence


_STATUS_KEYS = ("supported", "partial", "hypothesis", "disputed", "rejected")


def build_research_reliability(
    department_reports: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Summarize semantic validation without exposing raw gate internals."""

    counts = {key: 0 for key in _STATUS_KEYS}
    input_claims = 0
    reader_claims = 0
    warnings: List[str] = []
    audited_reports = 0
    cio_report = _first_agent(department_reports, {"CIOAgent", "DecisionReportAgent"})

    for report in department_reports:
        semantic = report.get("semanticValidation") or report.get("semantic_validation")
        if not isinstance(semantic, Mapping):
            continue
        audited_reports += 1
        input_claims += _as_int(semantic.get("inputClaimCount"))
        reader_claims += _as_int(semantic.get("readerClaimCount"))
        for collection in ("claims", "counterpoints", "nextActions"):
            for row in semantic.get(collection) or []:
                if not isinstance(row, Mapping):
                    continue
                status = str(row.get("status") or "").lower()
                if status in counts:
                    counts[status] += 1

    cio_semantic = {}
    if isinstance(cio_report, Mapping):
        value = cio_report.get("semanticValidation") or cio_report.get("semantic_validation")
        if isinstance(value, Mapping):
            cio_semantic = dict(value)
    audited = audited_reports > 0
    headline_safe = bool(cio_semantic) and _as_int(cio_semantic.get("readerClaimCount")) > 0
    summary_validation = cio_semantic.get("summary")
    if isinstance(summary_validation, Mapping):
        headline_safe = str(summary_validation.get("status") or "").lower() in {
            "supported",
            "partial",
            "hypothesis",
            "disputed",
        }

    if not audited:
        warnings.append("旧报告未执行结论语义相关性检查。")
    if counts["rejected"]:
        warnings.append(f"{counts['rejected']} 条无支撑说法已从读者报告移除。")
    conditional_count = counts["hypothesis"] + counts["disputed"]
    if conditional_count:
        warnings.append(f"{conditional_count} 条推断以待验证情景呈现。")
    if audited and not headline_safe:
        warnings.append("CIO 总结尚未通过语义可靠性检查。")

    decisive = counts["supported"] + counts["partial"] + conditional_count
    supported_ratio = counts["supported"] / decisive if decisive else 0.0
    if not audited:
        label = "待语义复核"
    elif not headline_safe:
        label = "结论不足"
    elif counts["rejected"] or conditional_count:
        label = "可用，含待确认情景"
    elif supported_ratio >= 0.75:
        label = "较高可信"
    else:
        label = "中等可信"

    return {
        "schema": "research_reliability_v1",
        "label": label,
        "audited": audited,
        "headlineSafe": headline_safe,
        "inputClaims": input_claims,
        "readerClaims": reader_claims,
        "supportedClaims": counts["supported"],
        "partialClaims": counts["partial"],
        "hypothesisClaims": counts["hypothesis"],
        "disputedClaims": counts["disputed"],
        "rejectedClaims": counts["rejected"],
        "warnings": warnings,
    }


def build_scenario_adjudication(
    department_reports: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Build one explicit base/alternative/CIO decision block.

    If a model emitted a structured adjudication, use it.  Otherwise derive a
    conservative version from already validated department claims.  This is a
    presentation adapter, not a second research engine.
    """

    cio = _first_agent(department_reports, {"CIOAgent", "DecisionReportAgent"}) or {}
    red = _first_agent(department_reports, {"RedTeamAgent", "RedBlueAgent"}) or {}

    # Only use a model adjudication after the semantic gate marked the object
    # as validated.  Otherwise derive a conservative product block from the
    # already-sanitized memo fields.
    semantic = cio.get("semanticValidation") or cio.get("semantic_validation")
    adjudication_audit = semantic.get("adjudication") if isinstance(semantic, Mapping) else {}
    model_adjudication = cio.get("adjudication") if isinstance(cio.get("adjudication"), Mapping) else {}
    use_model_adjudication = bool(
        isinstance(adjudication_audit, Mapping)
        and adjudication_audit.get("validated")
        and model_adjudication
    )
    shared = _supported_claims(department_reports, limit=3)
    base_case = _text(cio.get("summaryForReader") or cio.get("summary_for_reader"))
    alternative = _first_text(
        red.get("counterpoints"),
        red.get("keyClaims"),
        red.get("key_claims"),
    )
    judgment = _text(cio.get("summaryForReader") or cio.get("summary_for_reader"))
    why = _first_text(cio.get("keyClaims"), cio.get("key_claims"))
    triggers = _text_list(cio.get("nextActions") or cio.get("nextAction") or cio.get("next_action"), limit=3)

    if use_model_adjudication:
        shared = _adjudication_field_texts(
            adjudication_audit,
            "sharedFacts",
            fallback=model_adjudication.get("sharedFacts"),
            limit=3,
        ) or shared
        # A model adjudication is a scenario editor, not a fresh evidence
        # source.  Fields softened because of unsupported flow, valuation or
        # causal language must not outrank the already validated atomic CIO
        # claims in the public report.
        model_judgment = _adjudication_field_text(
            adjudication_audit,
            "judgment",
            fallback=model_adjudication.get("judgment"),
        )
        # Use the gate's safe text even when the field remains a hypothesis.
        # A base case is allowed to be an interpretation; it must not silently
        # inherit unrelated prose from the CIO judgment block.
        audited_base_case = _adjudication_field_text(
            adjudication_audit,
            "baseCase",
            fallback=model_adjudication.get("baseCase"),
        )
        base_case = (
            audited_base_case
            if _adjudication_field_is_clean(adjudication_audit, "baseCase")
            or _adjudication_field_has_safe_text(adjudication_audit, "baseCase")
            else model_judgment
        ) or model_judgment or base_case
        alternative = _adjudication_field_text(
            adjudication_audit,
            "strongestAlternative",
            fallback=model_adjudication.get("strongestAlternative"),
        ) or alternative
        if _adjudication_field_status(adjudication_audit, "strongestAlternative") in {"hypothesis", "disputed"}:
            alternative = _conditional_scenario(alternative)
        judgment = model_judgment or judgment
        validated_cio_reasons = _validated_claim_texts(cio, statuses={"supported", "partial"}, limit=2)
        why = (
            _adjudication_field_text(
                adjudication_audit,
                "why",
                fallback=model_adjudication.get("why"),
            )
            if _adjudication_field_is_clean(adjudication_audit, "why")
            else "；".join(validated_cio_reasons)
        ) or why
        triggers = _adjudication_field_texts(
            adjudication_audit,
            "invalidationTriggers",
            fallback=model_adjudication.get("invalidationTriggers"),
            limit=3,
        ) or triggers

    return {
        "schema": "scenario_adjudication_v1",
        "sharedFacts": shared,
        "baseCase": base_case or "当前基准情景尚未形成。",
        "strongestAlternative": alternative or "暂无形成证据链的竞争情景。",
        "judgment": judgment or "证据不足以形成最终裁决。",
        "why": why,
        "invalidationTriggers": triggers,
    }


def build_challenge_verdicts(
    department_reports: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Match validated RedTeam challenges back to the exact department claim.

    A challenge is not an automatic rejection.  It means the original claim
    must stop appearing as an uncontested supporting reason until CIO or new
    evidence resolves it.
    """

    claim_index: Dict[str, Dict[str, Any]] = {}
    for report in department_reports:
        agent = str(report.get("agent") or "")
        semantic = report.get("semanticValidation") or report.get("semantic_validation")
        semantic_rows = semantic.get("claims") if isinstance(semantic, Mapping) else []
        status_by_id = {
            str(row.get("claimId") or ""): str(row.get("status") or "")
            for row in semantic_rows or []
            if isinstance(row, Mapping)
        }
        safe_by_id = {
            str(row.get("claimId") or ""): _text(row.get("safeText") or row.get("text"))
            for row in semantic_rows or []
            if isinstance(row, Mapping)
        }
        for mapping in report.get("claimEvidence") or report.get("claim_evidence") or []:
            if not isinstance(mapping, Mapping):
                continue
            claim_id = str(mapping.get("claimId") or "")
            if not claim_id:
                continue
            claim_index[claim_id] = {
                "department": agent,
                "claim": safe_by_id.get(claim_id) or _text(mapping.get("claim")),
                "originalStatus": status_by_id.get(claim_id) or str(mapping.get("semanticStatus") or ""),
            }

    red = _first_agent(department_reports, {"RedTeamAgent", "RedBlueAgent"}) or {}
    semantic = red.get("semanticValidation") or red.get("semantic_validation")
    challenge_audit = semantic.get("challenges") if isinstance(semantic, Mapping) else {}
    audit_rows = challenge_audit.get("challenges") if isinstance(challenge_audit, Mapping) else []
    audit_by_target = {
        str(row.get("targetClaimId") or ""): row
        for row in audit_rows or []
        if isinstance(row, Mapping) and str(row.get("targetClaimId") or "")
    }

    verdicts: List[Dict[str, Any]] = []
    for challenge in red.get("challenges") or []:
        if not isinstance(challenge, Mapping):
            continue
        target_id = str(challenge.get("targetClaimId") or "")
        target = claim_index.get(target_id)
        if not target:
            continue
        audit = audit_by_target.get(target_id) or {}
        validation_status = str(challenge.get("validationStatus") or audit.get("status") or "unvalidated")
        if validation_status == "rejected":
            continue
        original_status = str(target.get("originalStatus") or "")
        verdicts.append({
            "targetClaimId": target_id,
            "department": str(target.get("department") or ""),
            "claim": str(target.get("claim") or ""),
            "originalStatus": original_status,
            "verdict": "withdrawn" if original_status == "rejected" else "challenged",
            "issueType": str(challenge.get("issueType") or "alternative_cause"),
            "opposingScenario": _text(challenge.get("opposingScenario")),
            "falsifier": _text(challenge.get("falsifier")),
            "evidenceIds": [str(item) for item in challenge.get("evidence_ids") or [] if str(item)],
            "validationStatus": validation_status,
        })
    return verdicts


def _supported_claims(rows: Sequence[Mapping[str, Any]], *, limit: int) -> List[str]:
    out: List[str] = []
    for row in rows:
        if str(row.get("agent") or "") in {"CIOAgent", "DecisionReportAgent", "RedTeamAgent", "RedBlueAgent"}:
            continue
        semantic = row.get("semanticValidation") or row.get("semantic_validation")
        if not isinstance(semantic, Mapping):
            continue
        accepted_ids = {
            str(item.get("claimId") or "")
            for item in semantic.get("claims") or []
            if isinstance(item, Mapping) and str(item.get("status") or "") == "supported"
        }
        if not accepted_ids:
            continue
        mappings = row.get("claimEvidence") or row.get("claim_evidence") or []
        for mapping in mappings:
            if not isinstance(mapping, Mapping):
                continue
            if str(mapping.get("claimId") or "") not in accepted_ids:
                continue
            text = _text(mapping.get("claim"))
            if text and text not in out:
                out.append(text)
                if len(out) >= limit:
                    return out
    return out


def _first_agent(rows: Sequence[Mapping[str, Any]], names: set[str]) -> Mapping[str, Any] | None:
    return next((row for row in rows if str(row.get("agent") or "") in names), None)


def _adjudication_field_is_clean(audit: Mapping[str, Any], field: str) -> bool:
    fields = audit.get("fields") if isinstance(audit, Mapping) else {}
    rows = fields.get(field) if isinstance(fields, Mapping) else None
    if not isinstance(rows, list) or not rows:
        # Backward-compatible artifacts only exposed ``validated``.
        return True
    severe = {
        "capital_flow_language_requires_flow_evidence",
        "valuation_label_requires_valuation_evidence",
        "corporate_action_does_not_prove_price_support",
        "deleveraging_requires_flow_or_leverage_evidence",
        "strong_causal_language_requires_direct_mechanism_evidence",
        "causal_attribution_requires_mechanism_evidence",
        "market_intensity_requires_market_benchmark",
        "market_stat_not_supported_by_cited_evidence",
    }
    return all(
        isinstance(row, Mapping)
        and str(row.get("status") or "") in {"supported", "partial"}
        and not severe.intersection(str(reason) for reason in row.get("reasons") or [])
        for row in rows
    )


def _adjudication_field_rows(audit: Mapping[str, Any], field: str) -> List[Mapping[str, Any]]:
    fields = audit.get("fields") if isinstance(audit, Mapping) else {}
    rows = fields.get(field) if isinstance(fields, Mapping) else None
    return [row for row in rows or [] if isinstance(row, Mapping)] if isinstance(rows, list) else []


def _adjudication_field_texts(
    audit: Mapping[str, Any],
    field: str,
    *,
    fallback: Any,
    limit: int,
) -> List[str]:
    rows = _adjudication_field_rows(audit, field)
    values = [
        _text(row.get("safeText") or row.get("text"))
        for row in rows
        if str(row.get("status") or "") != "rejected"
    ]
    clean = [value for value in values if value]
    # Once field-level validation exists it is the trust boundary. Falling back
    # to the raw model payload when every audited row was rejected would publish
    # exactly the text the validator removed. Legacy artifacts without rows keep
    # the old fallback behavior.
    if rows:
        return clean[:limit]
    return _text_list(fallback, limit=limit)


def _adjudication_field_text(audit: Mapping[str, Any], field: str, *, fallback: Any) -> str:
    values = _adjudication_field_texts(audit, field, fallback=fallback, limit=1)
    return values[0] if values else ""


def _adjudication_field_status(audit: Mapping[str, Any], field: str) -> str:
    rows = _adjudication_field_rows(audit, field)
    statuses = {str(row.get("status") or "").lower() for row in rows}
    if "rejected" in statuses:
        return "rejected"
    if "disputed" in statuses:
        return "disputed"
    if "hypothesis" in statuses:
        return "hypothesis"
    if "partial" in statuses:
        return "partial"
    return "supported" if "supported" in statuses else ""


def _adjudication_field_has_safe_text(audit: Mapping[str, Any], field: str) -> bool:
    return any(_text(row.get("safeText")) for row in _adjudication_field_rows(audit, field))


def _conditional_scenario(value: Any) -> str:
    text = _text(value)
    if not text or text.startswith(("若", "如果", "一旦")):
        return text
    return f"若后续证据支持这一情景：{text}"


def _validated_claim_texts(
    report: Mapping[str, Any],
    *,
    statuses: set[str],
    limit: int,
) -> List[str]:
    semantic = report.get("semanticValidation") or report.get("semantic_validation")
    status_by_id = {
        str(row.get("claimId") or ""): str(row.get("status") or "")
        for row in (semantic.get("claims") if isinstance(semantic, Mapping) else []) or []
        if isinstance(row, Mapping)
    }
    out: List[str] = []
    for row in report.get("claimEvidence") or report.get("claim_evidence") or []:
        if not isinstance(row, Mapping):
            continue
        if status_by_id.get(str(row.get("claimId") or "")) not in statuses:
            continue
        value = _text(row.get("claim"))
        if value and value not in out:
            out.append(value)
            if len(out) >= limit:
                break
    return out


def _first_text(*values: Any) -> str:
    for value in values:
        rows = _text_list(value, limit=1)
        if rows:
            return rows[0]
    return ""


def _text_list(value: Any, *, limit: int) -> List[str]:
    if isinstance(value, Mapping):
        raw: Iterable[Any] = value.values()
    elif isinstance(value, (list, tuple)):
        raw = value
    elif value in (None, ""):
        raw = ()
    else:
        raw = (value,)
    out: List[str] = []
    for item in raw:
        text = _text(item)
        if text and text not in out:
            out.append(text)
            if len(out) >= limit:
                break
    return out


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
