"""Audit data flow from providers to department agents and Reader.

The audit answers one concrete product question: when a department says "data
missing", is the data actually absent, not converted to evidence, not included
in the department context pack, not referenced by the Agent, or just not shown
in the Reader?
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from src.department_data_profiles import DEPARTMENT_DATA_PROFILES, department_profile_payload


AUDIT_SCHEMA = "department_data_audit_v1"


def write_department_data_audit(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    docs = Path(docs_dir)
    acceptance_dir = docs / "local_acceptance" / run_date
    acceptance_dir.mkdir(parents=True, exist_ok=True)
    payload = build_department_data_audit(docs, run_date)
    json_path = acceptance_dir / "department_data_audit.json"
    md_path = acceptance_dir / "department_data_audit.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_department_data_audit_md(payload), encoding="utf-8")
    return {
        "schema": "department_data_audit_written_v1",
        "runDate": run_date,
        "json": str(json_path.relative_to(docs)),
        "markdown": str(md_path.relative_to(docs)),
        "departments": len(payload.get("departments") or []),
        "blockingDepartments": sum(1 for row in payload.get("departments") or [] if row.get("status") != "ok"),
    }


def build_department_data_audit(docs: Path, run_date: str) -> Dict[str, Any]:
    run = docs / "run_status" / run_date
    provider_rows = _read_jsonl(run / "provider_runs.jsonl")
    evidence_rows = _read_jsonl(run / "evidence_ledger.jsonl")
    original_refs = _read_jsonl(run / "original_analysis_refs.jsonl")
    artifact = _read_json(docs / "reports" / f"{run_date}.artifact.json") or {}
    department_reports = artifact.get("departmentReports") if isinstance(artifact.get("departmentReports"), list) else []
    department_inputs = artifact.get("departmentInputs") if isinstance(artifact.get("departmentInputs"), list) else []
    reader_cards = ((artifact.get("readerV3") or {}).get("departmentCards") or []) if isinstance(artifact.get("readerV3"), Mapping) else []

    rows = [
        _department_row(profile.agent, provider_rows, evidence_rows, original_refs, department_reports, department_inputs, reader_cards)
        for profile in DEPARTMENT_DATA_PROFILES
    ]
    return {
        "schema": AUDIT_SCHEMA,
        "runDate": run_date,
        "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "summary": {
            "providerRows": len(provider_rows),
            "evidenceRows": len(evidence_rows),
            "originalRefs": len(original_refs),
            "departments": len(rows),
            "ok": sum(1 for row in rows if row["status"] == "ok"),
            "needsAttention": sum(1 for row in rows if row["status"] != "ok"),
        },
        "departments": rows,
    }


def render_department_data_audit_md(payload: Mapping[str, Any]) -> str:
    lines = [
        f"# Department Data Audit — {payload.get('runDate')}",
        "",
        "链路口径：源是否取到 → Evidence 是否生成 → Agent 是否拿到 → Agent 是否引用 → Reader 是否展示。",
        "",
        "## Summary",
        "",
    ]
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    for key in ("providerRows", "evidenceRows", "originalRefs", "departments", "ok", "needsAttention"):
        lines.append(f"- {key}: {summary.get(key, 0)}")
    lines.extend(
        [
            "",
            "## Department Matrix",
            "",
            "| Department | Status | Provider | Evidence | Context | Agent | Reader | Missing Chain |",
            "|---|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for row in payload.get("departments") or []:
        chain = "、".join(row.get("missingChain") or []) or "无"
        lines.append(
            "| {label} | {status} | {provider_success}/{provider_called} | {evidence_count} | {context_refs} | {agent_refs} | {reader} | {chain} |".format(
                label=_md(row.get("label") or row.get("agent")),
                status=row.get("status"),
                provider_success=row.get("providerSuccessCount", 0),
                provider_called=row.get("providerCallCount", 0),
                evidence_count=row.get("evidenceCount", 0),
                context_refs=row.get("contextEvidenceRefs", 0),
                agent_refs=row.get("agentEvidenceRefs", 0),
                reader="yes" if row.get("readerDisplayed") else "no",
                chain=_md(chain),
            )
        )
    lines.extend(["", "## Details", ""])
    for row in payload.get("departments") or []:
        lines.extend(
            [
                f"### {_md(row.get('label') or row.get('agent'))}",
                "",
                f"- Agent: `{row.get('agent')}`",
                f"- Input profile: `{row.get('inputProfile')}`",
                f"- Evidence domains: {', '.join(row.get('evidenceDomains') or []) or 'none'}",
                f"- Agent context original refs: {row.get('contextOriginalRefs', 0)}",
                f"- Available matching original refs: {row.get('originalRefCount', 0)}",
                f"- Agent output: {'yes' if row.get('agentOutputPresent') else 'no'}",
                f"- Reader displayed: {'yes' if row.get('readerDisplayed') else 'no'}",
                f"- Missing chain: {', '.join(row.get('missingChain') or []) or 'none'}",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _department_row(
    agent: str,
    provider_rows: List[Dict[str, Any]],
    evidence_rows: List[Dict[str, Any]],
    original_refs: List[Dict[str, Any]],
    department_reports: List[Dict[str, Any]],
    department_inputs: List[Dict[str, Any]],
    reader_cards: List[Dict[str, Any]],
) -> Dict[str, Any]:
    profile = department_profile_payload(agent)
    domains = {str(item) for item in profile.get("evidenceDomains") or [] if str(item)}
    provider_matches = [row for row in provider_rows if not domains or str(row.get("domain") or row.get("data_type") or "") in domains]
    evidence_matches = [row for row in evidence_rows if not domains or str(row.get("domain") or "") in domains]
    context = next((row for row in department_inputs if row.get("agent") == agent), {})
    report = next((row for row in department_reports if row.get("agent") == agent), {})
    card = next((row for row in reader_cards if row.get("agent") == agent), {})
    original_matches = [
        row
        for row in original_refs
        if agent in [str(item) for item in row.get("agentTargets") or []]
        or str(row.get("kind") or "") in {str(item) for item in profile.get("originalKinds") or []}
    ]
    missing_chain = _missing_chain(
        provider_matches=provider_matches,
        evidence_matches=evidence_matches,
        context=context,
        report=report,
        card=card,
    )
    return {
        "agent": agent,
        "label": _agent_label(agent),
        "inputProfile": profile.get("inputProfile"),
        "sourceKinds": profile.get("sourceKinds") or [],
        "originalKinds": profile.get("originalKinds") or [],
        "evidenceDomains": sorted(domains),
        "providerCallCount": len(provider_matches),
        "providerSuccessCount": sum(1 for row in provider_matches if _provider_success(row)),
        "evidenceCount": len(evidence_matches),
        "contextEvidenceRefs": len(context.get("evidenceIds") or []),
        "contextOriginalRefs": len(context.get("originalAnalysisRefs") or []),
        "originalRefCount": len(original_matches),
        "agentOutputPresent": bool(report.get("summaryForReader") or report.get("keyClaims")),
        "agentEvidenceRefs": len(report.get("evidenceIds") or []),
        "readerDisplayed": bool(card or report.get("readerVisible")),
        "missingChain": missing_chain,
        "status": "ok" if not missing_chain else "needs_attention",
    }


def _missing_chain(
    *,
    provider_matches: List[Mapping[str, Any]],
    evidence_matches: List[Mapping[str, Any]],
    context: Mapping[str, Any],
    report: Mapping[str, Any],
    card: Mapping[str, Any],
) -> List[str]:
    chain: List[str] = []
    if not provider_matches:
        chain.append("provider_not_called")
    elif not any(_provider_success(row) for row in provider_matches):
        chain.append("provider_no_success")
    if not evidence_matches:
        chain.append("evidence_not_created")
    if evidence_matches and not (context.get("evidenceIds") or context.get("originalAnalysisRefs")):
        chain.append("context_pack_missing")
    if not (report.get("summaryForReader") or report.get("keyClaims")):
        chain.append("agent_output_missing")
    if evidence_matches and report and not report.get("evidenceIds"):
        chain.append("agent_not_referencing_evidence")
    if report and not (card or report.get("readerVisible")):
        chain.append("reader_not_displayed")
    return chain


def _provider_success(row: Mapping[str, Any]) -> bool:
    status = str(row.get("status") or "").lower()
    if status:
        return status == "success"
    return bool(row.get("success")) and int(row.get("record_count") or row.get("recordCount") or 0) >= 0


def _agent_label(agent: str) -> str:
    return {
        "MacroAgent": "宏观部门",
        "GeoPolicyAgent": "地缘政策部门",
        "MarketAgent": "市场部门",
        "SectorAgent": "行业/风格部门",
        "FundamentalAgent": "基本面部门",
        "TechnicalAgent": "技术面部门",
        "IntelAgent": "新闻情报部门",
        "PortfolioAgent": "持仓部门",
        "RiskAgent": "风险部门",
        "RedTeamAgent": "红队反证",
        "CIOAgent": "CIO 总结",
    }.get(agent, agent)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")
