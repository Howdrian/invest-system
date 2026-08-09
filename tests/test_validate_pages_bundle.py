import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


def _load_module():
    path = Path("scripts/validate_pages_bundle.py")
    spec = importlib.util.spec_from_file_location("validate_pages_bundle", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, text: str = "ok") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimum_bundle(docs: Path, date: str, *, fatal: bool = True, raw_count: int = 1) -> None:
    compact = date.replace("-", "")
    for rel in [
        "index.html",
        f"reports/{date}.html",
        f"reports/{date}.artifact.json",
        f"reports/{date}.diagnostics.html",
        f"reports/{date}/macro.html",
        f"reports/{date}/geo.html",
        f"reports/{date}/market.html",
        f"reports/{date}/news.html",
        f"reports/{date}/stocks.html",
        f"reports/{date}/portfolio.html",
        f"reports/{date}/risk.html",
        f"daily/{date}.md",
        f"daily/{date}.html",
        f"agent_memos/{date}/index.html",
        f"market_cycle/{date}/summary.html",
        f"market_cycle/{date}/00_one_screen_brief.html",
        f"market_cycle/{date}/01_macro_review.html",
        f"market_cycle/{date}/09_screening_funnel.html",
        f"market_cycle/{date}/11_deep_review_queue.html",
        f"market_cycle/{date}/13_source_health.html",
        f"market_cycle/{date}/14_market_strategy.html",
        f"report_{compact}.md",
        f"report_{compact}.html",
    ]:
        _write(docs / rel, "<a href='#top'>self</a> 阻断")
    _write(docs / f"reports/{date}.html", f"<a href='../agent_memos/{date}/index.html'>Agent</a> 阻断")
    rows = [{"run_date": date, "code": "301013", "cio_status": "BLOCKED_BY_FATAL" if fatal else "PASS", "score": 0 if fatal else 8, "gate": "BLOCKED" if fatal else "PASS", "trade_plan": {"action": "no_action" if fatal else "watch"}}]
    _write(docs / "governed_results.json", json.dumps(rows, ensure_ascii=False))
    run_status = docs / "run_status" / date
    _write(run_status / "provider_runs.jsonl", json.dumps({"provider": "fixture", "success": True}, ensure_ascii=False) + "\n")
    _write(run_status / "evidence_ledger.jsonl", json.dumps({"id": "fixture:1", "domain": "macro", "fact_type": "verified_fact", "provider": "fixture", "source_url": "https://example.test"}, ensure_ascii=False) + "\n")
    _write(run_status / "source_health_v2.json", json.dumps({"schema": "source_health_v2", "overallMode": "LIMITED_REVIEW"}, ensure_ascii=False))
    run_matrix = {"schema": "run_matrix_v1", "runId": f"local-{date}-fixture", "runDate": date, "gitSha": "fixture", "symbols": ["301013"], "stages": []}
    _write(run_status / "run_matrix.json", json.dumps(run_matrix, ensure_ascii=False))
    artifact = {
        "schemaVersion": "report_artifact_v1",
        "artifactId": f"daily:{date}",
        "runDate": date,
        "generatedAt": "2026-06-19T08:00:00Z",
        "artifactType": "daily",
        "audience": "reader",
        "title": "日报",
        "summary": {
            "oneLine": "阻断",
            "keyFacts": ["事实"],
            "analysis": "推论",
            "finalConclusion": "结论",
            "nextSteps": ["下一步"],
        },
        "sections": [
            {"key": "source", "title": "数据源", "kind": "source", "contentMarkdown": "DB"},
            {"key": "facts", "title": "关键数据", "kind": "facts", "contentMarkdown": "事实"},
            {"key": "analysis", "title": "推论", "kind": "analysis", "contentMarkdown": "分析"},
            {"key": "final", "title": "总结论", "kind": "final_conclusion", "contentMarkdown": "结论"},
            {"key": "next", "title": "下一步", "kind": "next_steps", "contentMarkdown": "复核"},
        ],
        "provenance": {"origin": "invest-system.static", "sourceFiles": [], "generatedBy": "test"},
        "runMatrix": {"runId": run_matrix["runId"], "runDate": date},
        "evidenceItems": [{"id": "fixture:1"}],
        "departmentReports": [{"evidenceIds": ["fixture:1"]}],
        "readerV3": {
            "schema": "reader_v3_v1",
            "runDate": date,
            "hero": {
                "action": "不操作",
                "status": "多市场观察简报",
                "confidence": "低可信",
                "oneLine": "阻断",
                "maxLimitation": "数据不足",
                "marketStance": "市场状态待确认",
                "portfolioAction": "未接入真实持仓，不生成组合动作",
                "validity": "时点简报",
                "dataCoverage": "数据不足",
            },
            "marketMatrix": [],
            "stockMatrix": [],
            "adjudication": {},
            "reliability": {
                "headlineSafe": True,
                "headlineEvidenceSupported": True,
                "headlineStatus": "supported",
            },
            "reportSections": [],
            "departmentCards": [],
            "evidenceSummary": {},
        },
        "snapshotRefs": {
            "providerLedgerPath": f"run_status/{date}/provider_runs.jsonl",
            "evidenceLedgerPath": f"run_status/{date}/evidence_ledger.jsonl",
            "sourceHealthPath": f"run_status/{date}/source_health_v2.json",
            "runMatrixPath": f"run_status/{date}/run_matrix.json",
            "providerLedgerSha256": _sha(run_status / "provider_runs.jsonl"),
            "evidenceLedgerSha256": _sha(run_status / "evidence_ledger.jsonl"),
            "sourceHealthSha256": _sha(run_status / "source_health_v2.json"),
            "runMatrixSha256": _sha(run_status / "run_matrix.json"),
            "agentRunId": run_matrix["runId"],
        },
        "publish": {"jsonPath": f"docs/reports/{date}.artifact.json"},
        "quality": {"completeness": "partial", "missingFields": [], "validationErrors": []},
    }
    _write(docs / f"reports/{date}.artifact.json", json.dumps(artifact, ensure_ascii=False))
    for idx in range(raw_count):
        _write(
            docs / f"agent_memos/{date}/stocks/301013/{idx:02d}.json",
            json.dumps({"schema": "agent_memo_v1", "origin": "RAW_AGENT"}, ensure_ascii=False),
        )


def test_validate_pages_bundle_accepts_clean_bundle(tmp_path):
    mod = _load_module()
    date = "2026-06-19"
    _minimum_bundle(tmp_path, date)

    result = mod.validate_pages_bundle(date, tmp_path)

    assert result.ok is True
    assert result.agent_origin_counts["RAW_AGENT"] == 1
    assert result.broken_links == []


def test_validate_pages_bundle_flags_fatal_watch_wording(tmp_path):
    mod = _load_module()
    date = "2026-06-19"
    _minimum_bundle(tmp_path, date)
    compact = date.replace("-", "")
    _write(tmp_path / f"report_{compact}.md", "观望 — 治理层阻断 | 评分 50")

    result = mod.validate_pages_bundle(date, tmp_path)

    assert result.ok is False
    assert any("watch" in err or "score 50" in err for err in result.fatal_gate_errors)


def test_validate_pages_bundle_flags_forbidden_reader_phrases(tmp_path):
    mod = _load_module()
    date = "2026-06-19"
    _minimum_bundle(tmp_path, date)
    _write(tmp_path / f"reports/{date}.html", "静态 Pages Dashboard no_action RAW_AGENT {{ stale }} {% stale %} 原始报告（审计原文） N/A 阻断")

    result = mod.validate_pages_bundle(date, tmp_path)

    assert result.ok is False
    assert any("forbidden reader phrase" in err for err in result.semantic_errors)
    assert any("template block" in err for err in result.semantic_errors)


def test_validate_pages_bundle_allows_css_percent_closing_brace(tmp_path):
    mod = _load_module()
    date = "2026-06-19"
    _minimum_bundle(tmp_path, date)
    _write(tmp_path / f"reports/{date}.html", "<style>main{max-width:100%}</style><p>投研报告</p>")

    result = mod.validate_pages_bundle(date, tmp_path)

    assert not any("%}" in err for err in result.semantic_errors)


def test_validate_pages_bundle_flags_broken_links_and_bad_encoding(tmp_path):
    mod = _load_module()
    date = "2026-06-19"
    _minimum_bundle(tmp_path, date, raw_count=0)
    _write(tmp_path / f"reports/{date}.html", "<a href='../missing.html'>bad</a> � 阻断")

    result = mod.validate_pages_bundle(date, tmp_path)

    assert result.ok is False
    assert result.broken_links
    assert result.bad_encoding_files
    assert "governed run has no RAW_AGENT memos" in result.fatal_gate_errors


def test_validate_pages_bundle_rejects_link_outside_bundle(tmp_path):
    mod = _load_module()
    date = "2026-06-19"
    _minimum_bundle(tmp_path, date)
    outside = tmp_path.parent / "outside.html"
    _write(outside, "outside")
    _write(tmp_path / f"reports/{date}.html", "<a href='../../outside.html'>escape</a> 阻断")

    result = mod.validate_pages_bundle(date, tmp_path)

    assert result.ok is False
    assert result.broken_links == [
        f"reports/{date}.html -> ../../outside.html"
    ]


def test_validate_pages_bundle_rejects_symlink_link_outside_bundle(tmp_path):
    mod = _load_module()
    date = "2026-06-19"
    _minimum_bundle(tmp_path, date)
    outside = tmp_path.parent / "outside-linked.html"
    _write(outside, "outside")
    linked = tmp_path / "linked.html"
    os.symlink(outside, linked)
    _write(tmp_path / f"reports/{date}.html", "<a href='../linked.html'>escape</a> 阻断")

    result = mod.validate_pages_bundle(date, tmp_path)

    assert result.ok is False
    assert result.broken_links == [f"reports/{date}.html -> ../linked.html"]


@pytest.mark.parametrize("run_date", ["../../outside", "20260619", "2026-02-30"])
def test_validate_pages_bundle_rejects_invalid_run_date(tmp_path, run_date):
    mod = _load_module()

    with pytest.raises(ValueError, match="run_date"):
        mod.validate_pages_bundle(run_date, tmp_path)


def test_validate_pages_bundle_flags_blocked_trade_action_phrases(tmp_path):
    mod = _load_module()
    date = "2026-06-19"
    _minimum_bundle(tmp_path, date)
    compact = date.replace("-", "")
    _write(tmp_path / f"report_{compact}.html", "阻断 / 不操作 / 0% 但建议立即减仓或清仓止损，且有强烈买入信号")

    result = mod.validate_pages_bundle(date, tmp_path)

    assert result.ok is False
    assert any("blocked report contains trade action phrase" in err for err in result.fatal_gate_errors)


def test_validate_pages_bundle_flags_public_legacy_invest_brain_files(tmp_path):
    mod = _load_module()
    date = "2026-06-19"
    _minimum_bundle(tmp_path, date)
    _write(tmp_path / "invest-brain/2026-06-01/research-cycle/00_one_screen_brief.html", "legacy")

    result = mod.validate_pages_bundle(date, tmp_path)

    assert result.ok is False
    assert result.legacy_public_files == [
        "invest-brain/2026-06-01/research-cycle/00_one_screen_brief.html"
    ]
