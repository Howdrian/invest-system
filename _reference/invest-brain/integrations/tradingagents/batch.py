from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any
import argparse
import json

try:
    from ab_test import (
        SAMPLE_POOL,
        ab_dir_for,
        compare_protected_snapshots,
        init_sample,
        protected_snapshot,
    )
    from codex_native import init_codex_native_pool
    from completion_audit import completion_audit, render_markdown as render_completion_audit_markdown
    from run_sidecar import assert_provider_ready, main as run_sidecar_main
    from schemas import RESEARCH_ARCHIVE, archive_dir_for, assert_safe_output_path, write_json_safe, write_text_safe
except ImportError:  # pragma: no cover
    from .ab_test import (
        SAMPLE_POOL,
        ab_dir_for,
        compare_protected_snapshots,
        init_sample,
        protected_snapshot,
    )
    from .codex_native import init_codex_native_pool
    from .completion_audit import completion_audit, render_markdown as render_completion_audit_markdown
    from .run_sidecar import assert_provider_ready, main as run_sidecar_main
    from .schemas import RESEARCH_ARCHIVE, archive_dir_for, assert_safe_output_path, write_json_safe, write_text_safe


@dataclass
class BatchPlan:
    analysis_date: str
    sidecar_dirs: list[str]
    ab_sample_dirs: list[str]
    aggregate_dir: str
    protected_before: str
    protected_after: str
    protected_audit: str
    completion_audit_json: str
    completion_audit_md: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def aggregate_dir_for(analysis_date: str) -> Path:
    directory = RESEARCH_ARCHIVE / f"{analysis_date}-abtest-aggregate"
    assert_safe_output_path(directory)
    return directory


def batch_plan(analysis_date: str) -> BatchPlan:
    aggregate_dir = aggregate_dir_for(analysis_date)
    return BatchPlan(
        analysis_date=analysis_date,
        sidecar_dirs=[str(archive_dir_for(sample["ticker"], analysis_date)) for sample in SAMPLE_POOL],
        ab_sample_dirs=[str(ab_dir_for(sample["ticker"], analysis_date)) for sample in SAMPLE_POOL],
        aggregate_dir=str(aggregate_dir),
        protected_before=str(aggregate_dir / "protected_before.json"),
        protected_after=str(aggregate_dir / "protected_after.json"),
        protected_audit=str(aggregate_dir / "protected_audit.json"),
        completion_audit_json=str(aggregate_dir / "completion_audit.json"),
        completion_audit_md=str(aggregate_dir / "completion_audit.md"),
    )


def write_batch_plan(plan: BatchPlan, out: Path | None = None) -> None:
    if out is None:
        print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))
        return
    assert_safe_output_path(out)
    write_json_safe(out, plan.to_dict())
    print(out)


def init_ab_pool(analysis_date: str, force: bool = False) -> list[Path]:
    return [init_sample(sample["ticker"], analysis_date, force=force) for sample in SAMPLE_POOL]


def run_sidecar_pool(
    analysis_date: str,
    llm_provider: str,
    analysts: list[str],
    output_language: str,
    checkpoint: bool,
    quick_model: str | None,
    deep_model: str | None,
    backend_url: str | None,
    continue_on_error: bool,
) -> dict[str, Any]:
    assert_provider_ready(llm_provider, quick_model, deep_model)
    results: list[dict[str, Any]] = []
    for sample in SAMPLE_POOL:
        ticker = sample["ticker"]
        argv = [
            "--ticker", ticker,
            "--analysis-date", analysis_date,
            "--execute",
            "--llm-provider", llm_provider,
            "--output-language", output_language,
            "--analysts", *analysts,
        ]
        if checkpoint:
            argv.append("--checkpoint")
        if quick_model:
            argv.extend(["--quick-model", quick_model])
        if deep_model:
            argv.extend(["--deep-model", deep_model])
        if backend_url:
            argv.extend(["--backend-url", backend_url])
        try:
            run_sidecar_main(argv)
            results.append({"ticker": ticker, "status": "ok", "output_dir": str(archive_dir_for(ticker, analysis_date))})
        except SystemExit as exc:
            results.append({"ticker": ticker, "status": "error", "error": str(exc)})
            if not continue_on_error:
                break
        except Exception as exc:
            results.append({"ticker": ticker, "status": "error", "error": str(exc)})
            if not continue_on_error:
                break
    return {
        "analysis_date": analysis_date,
        "llm_provider": llm_provider,
        "results": results,
        "all_ok": all(item["status"] == "ok" for item in results) and len(results) == len(SAMPLE_POOL),
    }


def write_protected_snapshot(analysis_date: str, phase: str) -> Path:
    plan = batch_plan(analysis_date)
    if phase == "before":
        out = Path(plan.protected_before)
    elif phase == "after":
        out = Path(plan.protected_after)
    else:
        raise ValueError("phase must be 'before' or 'after'")
    write_json_safe(out, protected_snapshot())
    return out


def write_protected_audit(analysis_date: str) -> dict[str, Any]:
    plan = batch_plan(analysis_date)
    before = json.loads(Path(plan.protected_before).read_text(encoding="utf-8"))
    after = json.loads(Path(plan.protected_after).read_text(encoding="utf-8"))
    audit = compare_protected_snapshots(before, after)
    write_json_safe(Path(plan.protected_audit), audit)
    return audit


def write_completion_audit(analysis_date: str, evidence_mode: str = "sidecar") -> dict[str, Any]:
    plan = batch_plan(analysis_date)
    payload = completion_audit(analysis_date, [Path(plan.protected_audit)], evidence_mode=evidence_mode)
    write_json_safe(Path(plan.completion_audit_json), payload)
    write_text_safe(Path(plan.completion_audit_md), render_completion_audit_markdown(payload))
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch orchestration for TradingAgents sidecar integration.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--analysis-date", default=date.today().isoformat())
    plan_parser.add_argument("--out", type=Path)

    init_parser = subparsers.add_parser("init-ab")
    init_parser.add_argument("--analysis-date", default=date.today().isoformat())
    init_parser.add_argument("--force", action="store_true")

    init_codex_parser = subparsers.add_parser("init-codex-native")
    init_codex_parser.add_argument("--analysis-date", default=date.today().isoformat())
    init_codex_parser.add_argument("--force", action="store_true")

    snapshot_parser = subparsers.add_parser("snapshot-protected")
    snapshot_parser.add_argument("--analysis-date", default=date.today().isoformat())
    snapshot_parser.add_argument("--phase", choices=["before", "after"], required=True)

    audit_parser = subparsers.add_parser("audit-protected")
    audit_parser.add_argument("--analysis-date", default=date.today().isoformat())

    sidecar_parser = subparsers.add_parser("run-sidecars")
    sidecar_parser.add_argument("--analysis-date", default=date.today().isoformat())
    sidecar_parser.add_argument("--llm-provider", default="openai")
    sidecar_parser.add_argument("--quick-model")
    sidecar_parser.add_argument("--deep-model")
    sidecar_parser.add_argument("--backend-url")
    sidecar_parser.add_argument("--output-language", default="Chinese")
    sidecar_parser.add_argument("--analysts", nargs="+", default=["market", "news", "fundamentals"])
    sidecar_parser.add_argument("--checkpoint", action="store_true")
    sidecar_parser.add_argument("--continue-on-error", action="store_true")

    completion_parser = subparsers.add_parser("completion-audit")
    completion_parser.add_argument("--analysis-date", default=date.today().isoformat())
    completion_parser.add_argument("--evidence-mode", choices=["sidecar", "codex-native"], default="sidecar")

    args = parser.parse_args(argv)

    if args.command == "plan":
        write_batch_plan(batch_plan(args.analysis_date), args.out)
        return 0

    if args.command == "init-ab":
        for path in init_ab_pool(args.analysis_date, args.force):
            print(path)
        return 0

    if args.command == "init-codex-native":
        for path in init_codex_native_pool(args.analysis_date, args.force):
            print(path)
        return 0

    if args.command == "snapshot-protected":
        print(write_protected_snapshot(args.analysis_date, args.phase))
        return 0

    if args.command == "audit-protected":
        print(json.dumps(write_protected_audit(args.analysis_date), ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-sidecars":
        try:
            result = run_sidecar_pool(
                analysis_date=args.analysis_date,
                llm_provider=args.llm_provider,
                analysts=args.analysts,
                output_language=args.output_language,
                checkpoint=args.checkpoint,
                quick_model=args.quick_model,
                deep_model=args.deep_model,
                backend_url=args.backend_url,
                continue_on_error=args.continue_on_error,
            )
        except RuntimeError as exc:
            result = {
                "analysis_date": args.analysis_date,
                "llm_provider": args.llm_provider,
                "results": [],
                "all_ok": False,
                "error": str(exc),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["all_ok"] else 1

    if args.command == "completion-audit":
        payload = write_completion_audit(args.analysis_date, evidence_mode=args.evidence_mode)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["overall_passed"] else 1

    raise ValueError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
