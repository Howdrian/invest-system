"""Fork-specific GitHub Actions safety boundaries."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PR_REVIEW_WORKFLOW = ROOT / ".github" / "workflows" / "pr-review.yml"
DAILY_WORKFLOW = ROOT / ".github" / "workflows" / "00-daily-analysis.yml"


def _has_active_key(text: str, key: str) -> bool:
    return re.search(rf"^[ \t]*{re.escape(key)}[ \t]*:", text, flags=re.MULTILINE) is not None


def test_privileged_pr_review_never_checks_out_pull_request_code():
    workflow = PR_REVIEW_WORKFLOW.read_text(encoding="utf-8")

    assert not _has_active_key(workflow, "pull_request_target")
    assert not _has_active_key(workflow, "pull_request")
    assert "${{ github.event.pull_request.head.sha" not in workflow
    assert "ref: ${{ github.event.repository.default_branch }}" in workflow
    assert _has_active_key(workflow, "workflow_dispatch")
    assert "filename.startsWith('docker/')" in workflow


def test_daily_analysis_remains_manual_only_until_cloud_acceptance():
    workflow = DAILY_WORKFLOW.read_text(encoding="utf-8")

    assert _has_active_key(workflow, "workflow_dispatch")
    assert not _has_active_key(workflow, "schedule")


def test_public_actions_log_never_echoes_raw_runtime_log_tail():
    workflow = DAILY_WORKFLOW.read_text(encoding="utf-8")

    assert "tail -30 logs/" not in workflow
    assert "不回显原始运行日志" in workflow
