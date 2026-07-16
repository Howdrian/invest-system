#!/usr/bin/env python3
"""Write local acceptance notes without exposing secrets."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


FORBIDDEN_READER_TERMS = (
    "ReportArtifact",
    "sourceHealthV2",
    "providerMatrix",
    "RAW_AGENT",
    "DERIVED_FROM_ARTIFACT",
    "claimPolicy",
    "artifactId",
    "errorType",
    "fallbackTo",
    "recordCount",
    "runMatrix",
    "evidence_ledger",
    "provider_runs",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write baseline/final local acceptance report")
    parser.add_argument("--date", required=True)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--kind", choices=("baseline", "final"), required=True)
    parser.add_argument("--command-status", default="")
    args = parser.parse_args(argv)

    docs = Path(args.docs_dir)
    out_dir = docs / "local_acceptance" / args.date
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / ("baseline.md" if args.kind == "baseline" else "final_acceptance.md")
    path.write_text(_render(args.kind, docs, args.date, args.command_status), encoding="utf-8")
    print(json.dumps({"path": str(path), "kind": args.kind, "runDate": args.date}, ensure_ascii=False, indent=2))
    return 0


def _render(kind: str, docs: Path, run_date: str, command_status: str) -> str:
    artifact = _read_json(docs / "reports" / f"{run_date}.artifact.json") or {}
    health = _read_json(docs / "run_status" / run_date / "source_health_v2.json") or {}
    llm = _read_json(docs / "run_status" / run_date / "llm_agent_summary.json") or {}
    audit = _read_json(docs / "local_acceptance" / run_date / "department_data_audit.json") or {}
    html = _read_text(docs / "reports" / f"{run_date}.html")
    reliability = artifact.get("researchReliability") if isinstance(artifact.get("researchReliability"), Mapping) else {}
    enrichment = llm.get("cioEnrichment") if isinstance(llm.get("cioEnrichment"), Mapping) else artifact.get("cioEnrichment") or {}
    enrichment_summary = {
        key: enrichment.get(key)
        for key in ("requested", "requestCount", "successCount", "reusedCount", "failedCount", "remainingGaps")
        if key in enrichment
    }
    term_counts = {term: html.count(term) for term in FORBIDDEN_READER_TERMS}
    lines = [
        f"# Local {'Baseline' if kind == 'baseline' else 'Final Acceptance'} — {run_date}",
        "",
        f"- Generated at: {_now()}",
        f"- Git HEAD: {_git('rev-parse --short HEAD')}",
        f"- Dirty entries: {len([line for line in _git('status --short --untracked-files=all').splitlines() if line.strip()])}",
        f"- Report HTML: `docs/reports/{run_date}.html`",
        f"- Artifact JSON: `docs/reports/{run_date}.artifact.json`",
        f"- Diagnostics HTML: `docs/reports/{run_date}.diagnostics.html`",
        "",
        "## Report State",
        "",
        f"- analysisMode: `{artifact.get('analysisMode') or health.get('overallMode') or 'unknown'}`",
        f"- overallScore: `{(artifact.get('sourceHealthV2') or health).get('overallScore') if isinstance(artifact.get('sourceHealthV2') or health, Mapping) else 'unknown'}`",
        f"- evidenceStats: `{json.dumps(artifact.get('evidenceStats') or health.get('evidenceStats') or {}, ensure_ascii=False)}`",
        f"- researchReliability: `{reliability.get('label', 'unknown')}`",
        f"- hypothesisClaims: `{reliability.get('hypothesisClaims', 'unknown')}`",
        f"- rejectedClaims: `{reliability.get('rejectedClaims', 'unknown')}`",
        f"- CIO enrichment: `{json.dumps(enrichment_summary, ensure_ascii=False)}`",
        "",
        "## Reader Product Sections",
        "",
    ]
    reader_v3 = artifact.get("readerV3") if isinstance(artifact.get("readerV3"), Mapping) else {}
    report_sections = reader_v3.get("reportSections") if isinstance(reader_v3.get("reportSections"), list) else []
    if report_sections:
        lines.extend(f"- {row.get('title') or row.get('key')}" for row in report_sections if isinstance(row, Mapping))
    else:
        lines.append("- unknown")
    lines.extend([
        "",
        "## Agent State",
        "",
        f"- LLM success: `{llm.get('llmSuccessCount', 'unknown')}`",
        f"- fallback: `{llm.get('fallbackCount', 'unknown')}`",
        f"- selected model: `{llm.get('selectedModel', 'unknown')}`",
        "",
        "## Department Data Audit",
        "",
        f"- departments: `{(audit.get('summary') or {}).get('departments', 'unknown')}`",
        f"- needsAttention: `{(audit.get('summary') or {}).get('needsAttention', 'unknown')}`",
        f"- audit doc: `docs/local_acceptance/{run_date}/department_data_audit.md`",
        "",
        "## Reader Forbidden Field Counts",
        "",
    ])
    lines.extend(f"- `{term}`: {count}" for term, count in term_counts.items())
    if command_status:
        lines.extend(["", "## Command Status", "", command_status.strip(), ""])
    lines.extend([
        "",
        "## Manual Use",
        "",
        "Generate local report:",
        "",
        "```bash",
        "cd /Users/hac/AI-Studio/投研/invest-system-upstream-integration",
        f"scripts/run_research_daily_local.sh --date {run_date} --runtime llm --symbols \"600519,000001,AAPL,HK00700\"",
        "```",
        "",
        "Add `--with-original-analysis` only when original market/stock analysis must be regenerated; otherwise the local chain reuses the current runtime inputs.",
        "",
        "Open static report:",
        "",
        f"`/Users/hac/AI-Studio/投研/invest-system-upstream-integration/docs/reports/{run_date}.html`",
        "",
        "Open diagnostics:",
        "",
        f"`/Users/hac/AI-Studio/投研/invest-system-upstream-integration/docs/reports/{run_date}.diagnostics.html`",
        "",
        "Open Web panel:",
        "",
        "```bash",
        "cd /Users/hac/AI-Studio/投研/invest-system-upstream-integration",
        ".venv311/bin/python server.py",
        "```",
        "",
        "`http://localhost:8000/reports`",
    ])
    lines.extend(["", "## Notes", "", "- No cloud action was triggered by this local acceptance writer.", "- Secrets are not printed; only report paths and aggregate counts are recorded.", ""])
    return "\n".join(lines)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _git(args: str) -> str:
    try:
        return subprocess.check_output(["git", *args.split()], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
