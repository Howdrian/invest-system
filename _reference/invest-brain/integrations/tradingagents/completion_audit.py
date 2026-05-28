from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any
import argparse
import json

try:
    from ab_test import (
        SAMPLE_POOL,
        ab_dir_for,
        aggregate_gradings,
        load_gradings,
        load_protected_audits,
    )
    from schemas import (
        PROJECT_ROOT,
        RESEARCH_ARCHIVE,
        archive_dir_for,
        assert_safe_output_path,
        write_json_safe,
        write_text_safe,
    )
except ImportError:  # pragma: no cover
    from .ab_test import (
        SAMPLE_POOL,
        ab_dir_for,
        aggregate_gradings,
        load_gradings,
        load_protected_audits,
    )
    from .schemas import (
        PROJECT_ROOT,
        RESEARCH_ARCHIVE,
        archive_dir_for,
        assert_safe_output_path,
        write_json_safe,
        write_text_safe,
    )


REQUIRED_INTEGRATION_FILES = [
    "README.md",
    "STATUS.md",
    "schemas.py",
    "parse_report.py",
    "provider_config.py",
    "generate_challenge.py",
    "run_sidecar.py",
    "codex_native.py",
    "codex_native_workflow.md",
    "run_codex_native_ab.py",
    "ab_test.py",
    "batch.py",
    "completion_audit.py",
    "doctor.py",
    "setup_env.py",
    "ab_test_rubric.md",
    "fixtures/sample_complete_report.md",
]

REQUIRED_SIDECAR_FILES = [
    "research_plan.md",
    "tradingagents_metadata.json",
    "tradingagents_extract.json",
    "local_challenge.md",
]

REQUIRED_AB_FILES = [
    "a_old_flow.md",
    "b_with_tradingagents.md",
    "ab_grading.json",
    "grading.md",
    "summary.md",
]

SIDECAR_EVIDENCE_MARKERS = [
    "tradingagents_extract.json",
    "local_challenge.md",
]

CODEX_NATIVE_EVIDENCE_MARKERS = [
    "codex_native_plan.json",
    "codex_native_prompt.md",
]

EVIDENCE_MODES = {"sidecar", "codex-native"}


def has_placeholder_text(path: Path) -> bool:
    if not path.exists():
        return False
    text = path.read_text(encoding="utf-8")
    markers = ["TODO", "paste or generate", "待填写"]
    return any(marker.lower() in text.lower() for marker in markers)


def evidence_markers_for(evidence_mode: str) -> list[str]:
    if evidence_mode == "sidecar":
        return SIDECAR_EVIDENCE_MARKERS
    if evidence_mode == "codex-native":
        return CODEX_NATIVE_EVIDENCE_MARKERS
    raise ValueError(f"Unknown evidence mode: {evidence_mode}")


def ab_text_links_evidence(text: str, evidence_mode: str = "sidecar") -> bool:
    required_markers = evidence_markers_for(evidence_mode)
    lowered = text.lower()
    return all(marker.lower() in lowered for marker in required_markers)


def ab_text_links_sidecar_evidence(text: str) -> bool:
    return ab_text_links_evidence(text, "sidecar")


def ab_text_links_codex_native_evidence(text: str) -> bool:
    return ab_text_links_evidence(text, "codex-native")


@dataclass
class AuditItem:
    name: str
    passed: bool
    evidence: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def integration_dir() -> Path:
    return PROJECT_ROOT / "integrations" / "tradingagents"


def audit_integration_files() -> AuditItem:
    missing: list[str] = []
    evidence: list[str] = []
    root = integration_dir()
    for relative in REQUIRED_INTEGRATION_FILES:
        path = root / relative
        if path.exists():
            evidence.append(str(path.relative_to(PROJECT_ROOT)))
        else:
            missing.append(str(path.relative_to(PROJECT_ROOT)))
    return AuditItem(
        name="integration_files_present",
        passed=not missing,
        evidence=evidence,
        missing=missing,
    )


def audit_sidecar_outputs(analysis_date: str) -> AuditItem:
    missing: list[str] = []
    evidence: list[str] = []
    notes: list[str] = []
    for sample in SAMPLE_POOL:
        ticker = sample["ticker"]
        out_dir = archive_dir_for(ticker, analysis_date)
        if not out_dir.exists():
            missing.append(str(out_dir.relative_to(PROJECT_ROOT)))
            continue
        for filename in REQUIRED_SIDECAR_FILES:
            path = out_dir / filename
            if not path.exists():
                missing.append(str(path.relative_to(PROJECT_ROOT)))
        report_path = out_dir / "tradingagents_complete_report.md"
        state_path = out_dir / "tradingagents_full_state.json"
        if not report_path.exists() and not state_path.exists():
            missing.append(str((out_dir / "tradingagents_complete_report.md|tradingagents_full_state.json").relative_to(PROJECT_ROOT)))

        metadata_path = out_dir / "tradingagents_metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("mode") != "execute":
                notes.append(f"{ticker}: metadata mode is {metadata.get('mode')!r}, expected 'execute'")
        extract_path = out_dir / "tradingagents_extract.json"
        if extract_path.exists():
            extract = json.loads(extract_path.read_text(encoding="utf-8"))
            if str(extract.get("ticker", "")).upper() != str(ticker).upper():
                notes.append(f"{ticker}: extract ticker mismatch")
        challenge_path = out_dir / "local_challenge.md"
        if challenge_path.exists():
            challenge = challenge_path.read_text(encoding="utf-8")
            if "TradingAgents is external evidence only" not in challenge:
                notes.append(f"{ticker}: local_challenge missing external-evidence guard")
        evidence.append(str(out_dir.relative_to(PROJECT_ROOT)))

    return AuditItem(
        name="ten_real_sidecar_outputs",
        passed=not missing and not notes,
        evidence=evidence,
        missing=missing,
        notes=notes,
    )


def audit_codex_native_artifacts(analysis_date: str) -> AuditItem:
    missing: list[str] = []
    evidence: list[str] = []
    notes: list[str] = []
    for sample in SAMPLE_POOL:
        ticker = sample["ticker"]
        out_dir = ab_dir_for(ticker, analysis_date)
        if not out_dir.exists():
            missing.append(str(out_dir.relative_to(PROJECT_ROOT)))
            continue

        plan_path = out_dir / "codex_native_plan.json"
        prompt_path = out_dir / "codex_native_prompt.md"
        for path in [plan_path, prompt_path]:
            if not path.exists():
                missing.append(str(path.relative_to(PROJECT_ROOT)))

        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
            if plan.get("mode") != "codex_native":
                notes.append(f"{ticker}: codex_native_plan mode is {plan.get('mode')!r}, expected 'codex_native'")
            if str(plan.get("ticker", "")).upper() != str(ticker).upper():
                notes.append(f"{ticker}: codex_native_plan ticker mismatch")
            if plan.get("writeback_allowed") is not False:
                notes.append(f"{ticker}: codex_native_plan does not lock writeback_allowed=false")
        if prompt_path.exists():
            prompt = prompt_path.read_text(encoding="utf-8")
            for marker in CODEX_NATIVE_EVIDENCE_MARKERS:
                if marker not in prompt:
                    notes.append(f"{ticker}: codex_native_prompt missing {marker}")
        evidence.append(str(out_dir.relative_to(PROJECT_ROOT)))

    return AuditItem(
        name="ten_codex_native_artifacts",
        passed=not missing and not notes,
        evidence=evidence,
        missing=missing,
        notes=notes,
    )


def audit_ab_samples(analysis_date: str, evidence_mode: str = "sidecar") -> tuple[AuditItem, list[Path]]:
    missing: list[str] = []
    evidence: list[str] = []
    notes: list[str] = []
    grading_paths: list[Path] = []
    required_markers = evidence_markers_for(evidence_mode)
    for sample in SAMPLE_POOL:
        ticker = sample["ticker"]
        out_dir = ab_dir_for(ticker, analysis_date)
        if not out_dir.exists():
            missing.append(str(out_dir.relative_to(PROJECT_ROOT)))
            continue
        for filename in REQUIRED_AB_FILES:
            path = out_dir / filename
            if not path.exists():
                missing.append(str(path.relative_to(PROJECT_ROOT)))
            elif filename in {"a_old_flow.md", "b_with_tradingagents.md", "grading.md", "summary.md"} and has_placeholder_text(path):
                notes.append(f"{ticker}: {filename} still contains placeholder text")
        b_path = out_dir / "b_with_tradingagents.md"
        if b_path.exists() and not ab_text_links_evidence(b_path.read_text(encoding="utf-8"), evidence_mode):
            notes.append(
                f"{ticker}: b_with_tradingagents.md does not reference "
                f"{' and '.join(required_markers)}"
            )
        grading_path = out_dir / "ab_grading.json"
        if grading_path.exists():
            grading_paths.append(grading_path)
            grading = json.loads(grading_path.read_text(encoding="utf-8"))
            if str(grading.get("status", "")).lower() != "final":
                notes.append(f"{ticker}: ab_grading status is not final")
            notes_payload = grading.get("notes") or {}
            if str(grading.get("status", "")).lower() == "final":
                if grading.get("has_incremental_information") and not notes_payload.get("b_added"):
                    notes.append(f"{ticker}: final grading has incremental flag but empty notes.b_added")
                if not str(notes_payload.get("gate_check") or "").strip():
                    notes.append(f"{ticker}: final grading missing notes.gate_check")
        evidence.append(str(out_dir.relative_to(PROJECT_ROOT)))

    return AuditItem(
        name="ten_ab_samples_present_and_final",
        passed=not missing and not notes and len(grading_paths) == len(SAMPLE_POOL),
        evidence=evidence,
        missing=missing,
        notes=notes,
    ), grading_paths


def audit_protected_audits(paths: list[Path]) -> AuditItem:
    missing = [str(path.relative_to(PROJECT_ROOT)) for path in paths if not path.exists()]
    evidence: list[str] = []
    notes: list[str] = []
    if not paths:
        notes.append("No protected audit path supplied.")
    for path in paths:
        if not path.exists():
            continue
        audit = json.loads(path.read_text(encoding="utf-8"))
        evidence.append(str(path.relative_to(PROJECT_ROOT)))
        if audit.get("writeback_violation"):
            notes.append(f"{path.relative_to(PROJECT_ROOT)} reports writeback violation")
    return AuditItem(
        name="protected_file_audit_present_and_clean",
        passed=bool(paths) and not missing and not notes,
        evidence=evidence,
        missing=missing,
        notes=notes,
    )


def audit_ab_aggregate(grading_paths: list[Path], protected_audit_paths: list[Path]) -> AuditItem:
    missing: list[str] = []
    notes: list[str] = []
    evidence: list[str] = []
    if len(grading_paths) != len(SAMPLE_POOL):
        missing.append("all 10 ab_grading.json files")
    missing.extend(str(path.relative_to(PROJECT_ROOT)) for path in protected_audit_paths if not path.exists())
    if missing:
        return AuditItem(
            name="ab_aggregate_pass",
            passed=False,
            evidence=evidence,
            missing=missing,
            notes=notes,
        )
    result = aggregate_gradings(
        load_gradings(grading_paths),
        protected_audits=load_protected_audits(protected_audit_paths),
    )
    evidence.append(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    if result.verdict != "PASS":
        notes.append(f"A/B aggregate verdict is {result.verdict}, expected PASS")
        notes.extend(result.notes)
    return AuditItem(
        name="ab_aggregate_pass",
        passed=result.verdict == "PASS",
        evidence=evidence,
        missing=missing,
        notes=notes,
    )


def completion_audit(
    analysis_date: str,
    protected_audit_paths: list[Path] | None = None,
    evidence_mode: str = "sidecar",
) -> dict[str, Any]:
    if evidence_mode not in EVIDENCE_MODES:
        raise ValueError(f"Unknown evidence mode: {evidence_mode}")
    default_protected = RESEARCH_ARCHIVE / f"{analysis_date}-abtest-aggregate" / "protected_audit.json"
    protected_paths = protected_audit_paths if protected_audit_paths is not None else [default_protected]

    items: list[AuditItem] = []
    items.append(audit_integration_files())
    if evidence_mode == "sidecar":
        items.append(audit_sidecar_outputs(analysis_date))
        objective = (
            "TradingAgents read-only sidecar is integrated without redundant core architecture, "
            "10 real sidecar outputs exist, 10 required A/B samples are final, protected files "
            "were audited cleanly, and A/B aggregate verdict is PASS."
        )
    else:
        items.append(audit_codex_native_artifacts(analysis_date))
        objective = (
            "TradingAgents architecture is absorbed into a Codex-native workflow without redundant "
            "core architecture, 10 Codex-native A/B artifacts exist, 10 required A/B samples are final, "
            "protected files were audited cleanly, and A/B aggregate verdict is PASS."
        )
    ab_item, grading_paths = audit_ab_samples(analysis_date, evidence_mode)
    items.append(ab_item)
    items.append(audit_protected_audits(protected_paths))
    items.append(audit_ab_aggregate(grading_paths, protected_paths))

    return {
        "schema": "tradingagents_completion_audit_v2",
        "analysis_date": analysis_date,
        "evidence_mode": evidence_mode,
        "objective": objective,
        "overall_passed": all(item.passed for item in items),
        "items": [item.to_dict() for item in items],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# TradingAgents Completion Audit",
        "",
        f"- Analysis date: `{payload['analysis_date']}`",
        f"- Evidence mode: `{payload.get('evidence_mode', 'sidecar')}`",
        f"- Overall passed: `{payload['overall_passed']}`",
        "",
        "## Criteria",
        "",
    ]
    for item in payload["items"]:
        lines.append(f"### {item['name']}")
        lines.append("")
        lines.append(f"- Passed: `{item['passed']}`")
        if item["missing"]:
            lines.append("- Missing:")
            lines.extend(f"  - `{value}`" for value in item["missing"])
        if item["notes"]:
            lines.append("- Notes:")
            lines.extend(f"  - {value}" for value in item["notes"])
        if item["evidence"]:
            lines.append("- Evidence:")
            lines.extend(f"  - `{value}`" for value in item["evidence"][:20])
            if len(item["evidence"]) > 20:
                lines.append(f"  - ... {len(item['evidence']) - 20} more")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit whether TradingAgents integration goal is complete.")
    parser.add_argument("--analysis-date", default=date.today().isoformat())
    parser.add_argument("--evidence-mode", choices=sorted(EVIDENCE_MODES), default="sidecar")
    parser.add_argument("--protected-audit-json", type=Path, nargs="*")
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--md-out", type=Path)
    args = parser.parse_args(argv)

    payload = completion_audit(args.analysis_date, args.protected_audit_json, args.evidence_mode)

    if args.json_out:
        assert_safe_output_path(args.json_out)
        write_json_safe(args.json_out, payload)
    if args.md_out:
        assert_safe_output_path(args.md_out)
        write_text_safe(args.md_out, render_markdown(payload))

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
