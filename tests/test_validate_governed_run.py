import importlib.util
import json
from pathlib import Path


def _load_module():
    path = Path("scripts/validate_governed_run.py")
    spec = importlib.util.spec_from_file_location("validate_governed_run", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_validate_governed_run_requires_today_report_and_all_expected_symbols(tmp_path):
    mod = _load_module()
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "report_20260615.md").write_text("# today\n", encoding="utf-8")
    (reports / "report_20260601.md").write_text("# old\n", encoding="utf-8")
    (reports / "governed_results.json").write_text(
        json.dumps([
            {"run_date": "2026-06-15", "code": "600519"},
            {"run_date": "2026-06-01", "code": "000858"},
        ]),
        encoding="utf-8",
    )

    summary = mod.evaluate_governed_run(
        run_date="2026-06-15",
        mode="full",
        expected_symbols=["600519", "000858"],
        reports_dir=reports,
    )

    assert summary["status"] == "partial"
    assert summary["completed_symbols"] == ["600519"]
    assert summary["missing_symbols"] == ["000858"]
    assert summary["stale_reports_ignored"] == ["report_20260601.md"]
    assert "incomplete_governed_symbols" in summary["reasons"]


def test_validate_governed_run_fails_when_only_old_report_exists(tmp_path):
    mod = _load_module()
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "report_20260601.md").write_text("# old\n", encoding="utf-8")

    summary = mod.evaluate_governed_run(
        run_date="2026-06-15",
        mode="full",
        expected_symbols=["600519"],
        reports_dir=reports,
    )

    assert summary["status"] == "failed"
    assert "missing_today_report" in summary["reasons"]
    assert "missing_governed_results" in summary["reasons"]


def test_validate_governed_run_writes_status_files(tmp_path):
    mod = _load_module()
    reports = tmp_path / "reports"
    status_dir = tmp_path / "run_status"
    reports.mkdir()
    (reports / "report_20260615.md").write_text("# today\n", encoding="utf-8")
    (reports / "governed_results.json").write_text(
        json.dumps([{"run_date": "2026-06-15", "code": "600519"}]),
        encoding="utf-8",
    )

    summary = mod.evaluate_governed_run(
        run_date="2026-06-15",
        mode="full",
        expected_symbols=["600519"],
        reports_dir=reports,
    )
    mod.write_status(summary, status_dir)

    assert (status_dir / "stock_analysis_status.txt").read_text(encoding="utf-8") == "success"
    written = json.loads((status_dir / "governed_result_summary.json").read_text(encoding="utf-8"))
    assert written["governed_results_count"] == 1
