import json
from pathlib import Path

from src.source_health.department_data_audit import build_department_data_audit, write_department_data_audit


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def test_department_data_audit_tracks_provider_evidence_agent_reader_chain(tmp_path):
    docs = tmp_path / "docs"
    date = "2026-07-02"
    run = docs / "run_status" / date
    _write_jsonl(run / "provider_runs.jsonl", [
        {"provider": "FRED", "domain": "macro", "operation": "fred_series", "success": True, "record_count": 2},
        {"provider": "GDELT", "domain": "news_sentiment", "operation": "gdelt_doc", "success": True, "record_count": 3},
    ])
    _write_jsonl(run / "evidence_ledger.jsonl", [
        {"id": "fred:DGS10", "domain": "macro", "fact_type": "verified_fact"},
        {"id": "gdelt:1", "domain": "news_sentiment", "fact_type": "discovery"},
    ])
    _write_jsonl(run / "original_analysis_refs.jsonl", [
        {"kind": "geo_policy_seed", "status": "available", "agentTargets": ["GeoPolicyAgent"], "evidenceIds": ["gdelt:1"]},
    ])
    _write_json(docs / "reports" / f"{date}.artifact.json", {
        "departmentInputs": [
            {"agent": "GeoPolicyAgent", "evidenceIds": ["gdelt:1"], "originalAnalysisRefs": [{"kind": "geo_policy_seed"}]},
        ],
        "departmentReports": [
            {"agent": "GeoPolicyAgent", "summaryForReader": "地缘风险中性。", "evidenceIds": ["gdelt:1"], "readerVisible": True},
        ],
        "readerV2": {"departmentCards": [{"agent": "GeoPolicyAgent", "conclusion": "地缘风险中性。"}]},
    })

    payload = build_department_data_audit(docs, date)
    geo = next(row for row in payload["departments"] if row["agent"] == "GeoPolicyAgent")

    assert geo["status"] == "ok"
    assert geo["providerSuccessCount"] >= 1
    assert geo["evidenceCount"] >= 1
    assert geo["readerDisplayed"] is True

    result = write_department_data_audit(docs, date)
    assert (docs / result["markdown"]).exists()
