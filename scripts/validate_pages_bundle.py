# -*- coding: utf-8 -*-
"""Validate generated static Pages bundle for a single run date.

Checks only presentation artifacts. It does not run analysis and never touches
protected data or credentials.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.pages_publication import (
    build_pages_publication_manifest,
    validate_pages_run_date,
)
from src.report_policy import is_blocked_governed_row
from src.source_health.run_matrix import validate_snapshot_chain


@dataclass
class PagesBundleValidation:
    ok: bool
    run_date: str
    required_files_checked: int = 0
    links_checked: int = 0
    broken_links: list[str] = field(default_factory=list)
    bad_encoding_files: list[str] = field(default_factory=list)
    agent_origin_counts: dict[str, int] = field(default_factory=dict)
    fatal_gate_errors: list[str] = field(default_factory=list)
    semantic_errors: list[str] = field(default_factory=list)
    snapshot_errors: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    legacy_public_files: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "pages_bundle_validation_v1",
            "ok": self.ok,
            "run_date": self.run_date,
            "required_files_checked": self.required_files_checked,
            "links_checked": self.links_checked,
            "broken_links": self.broken_links,
            "bad_encoding_files": self.bad_encoding_files,
            "agent_origin_counts": self.agent_origin_counts,
            "fatal_gate_errors": self.fatal_gate_errors,
            "semantic_errors": self.semantic_errors,
            "snapshot_errors": self.snapshot_errors,
            "missing_files": self.missing_files,
            "legacy_public_files": self.legacy_public_files,
        }


BLOCKED_TRADE_ACTION_PHRASES = [
    "强烈买入信号",
    "买入信号",
    "立即减仓",
    "建议减仓",
    "建议卖出",
    "清仓",
    "止损",
]

FORBIDDEN_READER_PHRASES = [
    "静态 Pages Dashboard",
    "展示系统",
    "欠缺 / 低效",
    "原始报告（审计原文）",
    "原始审计",
    "BLOCKED_BY_FATAL",
    "FULL_REVIEW",
    "LIMITED_REVIEW",
    "SCREEN_ONLY",
    "OBSERVE_ONLY",
    "RAW_AGENT",
    "DERIVED_FROM_ARTIFACT",
    "ReportArtifact",
    "sourceHealthV2",
    "providerMatrix",
    "runMatrix",
    "errorType",
    "fallbackTo",
    "recordCount",
    "evidence_ledger",
    "provider_runs",
    "agent_reported_data_gap",
    "providerSummary",
    "originalAnalysisSummary",
    "Governed",
    "governed",
    "claimPolicy",
    "artifactId",
    "no_action",
]


def _iter_reader_html(docs_dir: Path, run_date: str, governed_rows: list[dict[str, Any]]) -> Iterable[Path]:
    yield from build_pages_publication_manifest(docs_dir, run_date, governed_rows).reader_html()


def _check_reader_semantics(docs_dir: Path, run_date: str, governed_rows: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for path in _iter_reader_html(docs_dir, run_date, governed_rows):
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(docs_dir)
        for phrase in FORBIDDEN_READER_PHRASES:
            if phrase in text:
                errors.append(f"{rel} contains forbidden reader phrase: {phrase}")
        if re.search(r"(?<![A-Za-z0-9])N/A(?![A-Za-z0-9])", text):
            errors.append(f"{rel} contains forbidden reader phrase: N/A")
        if re.search(r"\{\{\s*[^}]+\s*\}\}", text):
            errors.append(f"{rel} contains template placeholder")
        if re.search(r"\{%[\s\S]*?%\}", text):
            errors.append(f"{rel} contains template block")
    return errors


def _read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _governed_rows(docs_dir: Path, run_date: str) -> list[dict[str, Any]]:
    payload = _read_json(docs_dir / "governed_results.json")
    if not isinstance(payload, list):
        return []
    return [x for x in payload if isinstance(x, dict) and str(x.get("run_date") or run_date) == run_date]


def _is_fatal(row: dict[str, Any]) -> bool:
    return is_blocked_governed_row(row)


def _required_files(docs_dir: Path, run_date: str, governed_rows: list[dict[str, Any]]) -> list[Path]:
    return build_pages_publication_manifest(docs_dir, run_date, governed_rows).required_files()


def _iter_entry_html(docs_dir: Path, run_date: str, governed_rows: list[dict[str, Any]]) -> Iterable[Path]:
    yield from build_pages_publication_manifest(docs_dir, run_date, governed_rows).entry_html()


def _extract_links(html: str) -> list[str]:
    return re.findall(r"href=['\"]([^'\"]+)['\"]", html)


def _check_link(path: Path, href: str) -> Path | None:
    if href.startswith(("http://", "https://", "mailto:", "data:", "#")):
        return None
    clean = unquote(href.split("#", 1)[0].strip())
    if not clean:
        return None
    return (path.parent / clean).resolve()


def _is_within_bundle(path: Path, bundle_root: Path) -> bool:
    try:
        path.relative_to(bundle_root)
    except ValueError:
        return False
    return True


def _origin_counts(agent_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {"RAW_AGENT": 0, "DERIVED_FROM_ARTIFACT": 0, "MISSING": 0}
    if not agent_dir.exists():
        return counts
    for path in agent_dir.rglob("*.json"):
        payload = _read_json(path)
        if isinstance(payload, dict) and payload.get("schema") == "agent_memo_v1":
            origin = str(payload.get("origin") or "DERIVED_FROM_ARTIFACT")
            counts[origin] = counts.get(origin, 0) + 1
    return counts


def validate_pages_bundle(
    run_date: str,
    docs_dir: Path,
    *,
    public_only: bool = False,
) -> PagesBundleValidation:
    validate_pages_run_date(run_date)
    docs_dir = Path(docs_dir).expanduser().resolve(strict=False)
    rows = _governed_rows(docs_dir, run_date)
    result = PagesBundleValidation(ok=False, run_date=run_date)
    legacy_dir = docs_dir / "invest-brain"
    if legacy_dir.exists():
        result.legacy_public_files = [
            str(path.relative_to(docs_dir))
            for path in sorted(legacy_dir.rglob("*"))
            if path.is_file()
        ]

    manifest = build_pages_publication_manifest(docs_dir, run_date, rows)
    required = manifest.public_files() if public_only else _required_files(docs_dir, run_date, rows)
    result.required_files_checked = len(required)
    result.missing_files = [str(p.relative_to(docs_dir)) for p in required if not p.exists()]

    entry_html = manifest.public_html() if public_only else _iter_entry_html(docs_dir, run_date, rows)
    for path in entry_html:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "\ufffd" in text or "ï¿½" in text:
            result.bad_encoding_files.append(str(path.relative_to(docs_dir)))
        for href in _extract_links(text):
            target = _check_link(path, href)
            if target is None:
                continue
            result.links_checked += 1
            if not _is_within_bundle(target, docs_dir) or not target.exists():
                result.broken_links.append(f"{path.relative_to(docs_dir)} -> {href}")

    result.agent_origin_counts = (
        {} if public_only else _origin_counts(docs_dir / "agent_memos" / run_date)
    )
    if public_only:
        result.semantic_errors = []
        for path in manifest.public_html():
            text = path.read_text(encoding="utf-8", errors="replace")
            rel = path.relative_to(docs_dir)
            for phrase in FORBIDDEN_READER_PHRASES:
                if phrase in text:
                    result.semantic_errors.append(
                        f"{rel} contains forbidden reader phrase: {phrase}"
                    )
    else:
        result.semantic_errors = _check_reader_semantics(docs_dir, run_date, rows)
    artifact_path = docs_dir / "reports" / f"{run_date}.artifact.json"
    artifact_payload = _read_json(artifact_path)
    if artifact_payload is not None and not public_only:
        try:
            from src.report_artifact import validate_report_artifact

            ok, errors = validate_report_artifact(artifact_payload)
            if not ok:
                result.semantic_errors.append(f"reports/{run_date}.artifact.json invalid: {';'.join(errors)}")
            result.snapshot_errors.extend(validate_snapshot_chain(docs_dir, artifact_payload))
        except Exception as exc:
            result.semantic_errors.append(f"reports/{run_date}.artifact.json validation failed: {exc}")

    fatal_rows = [] if public_only else [row for row in rows if _is_fatal(row)]
    if fatal_rows:
        compact = run_date.replace("-", "")
        report_text = ""
        for rel in [Path("reports") / f"{run_date}.html", Path(f"report_{compact}.html"), Path(f"report_{compact}.md")]:
            path = docs_dir / rel
            if path.exists():
                report_text += "\n" + path.read_text(encoding="utf-8", errors="replace")
        if "评分 50" in report_text or "score 50" in report_text.lower():
            result.fatal_gate_errors.append("fatal report still shows score 50")
        if "观望 — 治理层阻断" in report_text:
            result.fatal_gate_errors.append("fatal report still uses watch wording")
        if "阻断" not in report_text and "BLOCKED" not in report_text:
            result.fatal_gate_errors.append("fatal report lacks blocked wording")
        for phrase in BLOCKED_TRADE_ACTION_PHRASES:
            if phrase in report_text:
                result.fatal_gate_errors.append(f"blocked report contains trade action phrase: {phrase}")
        if len(fatal_rows) == len(rows) and "观望:1" in report_text:
            result.fatal_gate_errors.append("all-fatal run is still counted as watch")
        if result.agent_origin_counts.get("RAW_AGENT", 0) <= 0:
            result.fatal_gate_errors.append("governed run has no RAW_AGENT memos")

    result.ok = not any([
        result.missing_files,
        result.broken_links,
        result.bad_encoding_files,
        result.fatal_gate_errors,
        result.semantic_errors,
        result.snapshot_errors,
        result.legacy_public_files,
    ])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate static Pages report bundle")
    parser.add_argument("--date", required=True, type=validate_pages_run_date)
    parser.add_argument("--docs-dir", default="docs")
    parser.add_argument("--output", default="")
    parser.add_argument("--fail-on-error", action="store_true")
    parser.add_argument("--public-only", action="store_true")
    args = parser.parse_args(argv)

    result = validate_pages_bundle(
        args.date,
        Path(args.docs_dir),
        public_only=args.public_only,
    )
    payload = result.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    if args.fail_on_error and not result.ok:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
