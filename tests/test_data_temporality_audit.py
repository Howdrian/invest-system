from __future__ import annotations

import json

from src.source_health.temporal import iso_timestamp


def test_iso_timestamp_preserves_date_only_precision():
    assert iso_timestamp("2026-07-17") == "2026-07-17"


def test_data_temporality_audit_accepts_timestamped_comparison_chain(tmp_path):
    from scripts.audit_data_temporality import audit_data_temporality
    from src.source_health.evidence_ledger import write_evidence_ledger
    from src.source_health.provider_ledger import write_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_dir = docs / "run_status" / run_date
    report_dir = docs / "reports"
    run_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    write_provider_ledger(run_dir / "provider_runs.jsonl", [{"provider": "DataFetcherManager", "success": True}])
    write_evidence_ledger(
        run_dir / "evidence_ledger.jsonl",
        [
            {
                "id": "price",
                "domain": "price",
                "metric": "price_history_comparison",
                "as_of": run_date,
                "event_time": f"{run_date}T08:00:00Z",
                "fetched_at": f"{run_date}T08:01:00Z",
                "provider": "DataFetcherManager",
                "raw_path": "run_status/example.jsonl",
                "fact_type": "derived_fact",
            },
            {
                "id": "universe",
                "domain": "price",
                "metric": "universe_price_comparison",
                "as_of": run_date,
                "provider": "DataFetcherManager",
                "raw_path": "run_status/example.jsonl",
                "fact_type": "derived_fact",
            },
            {
                "id": "macro",
                "domain": "macro",
                "metric": "DGS10_history_comparison",
                "as_of": run_date,
                "provider": "FRED",
                "source_url": "https://fred.stlouisfed.org/series/DGS10",
                "fact_type": "derived_fact",
            },
        ],
    )
    (report_dir / f"{run_date}.artifact.json").write_text(
        json.dumps({"readerV3": {"timing": {
            "dataAsOf": run_date,
            "generatedAt": f"{run_date}T09:00:00Z",
        }}}),
        encoding="utf-8",
    )

    result = audit_data_temporality(docs, run_date)

    assert result["ok"] is True
    assert result["providerObservedAtCoverage"] == 1.0
    assert result["evidenceAsOfCoverage"] == 1.0
    assert result["comparisonStatus"]["price"] is True
    assert result["comparisonStatus"]["macro"] is True


def test_data_temporality_audit_rejects_fetch_time_after_report_generation(tmp_path):
    from scripts.audit_data_temporality import audit_data_temporality
    from src.source_health.evidence_ledger import write_evidence_ledger
    from src.source_health.provider_ledger import write_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    run_dir = docs / "run_status" / run_date
    report_dir = docs / "reports"
    run_dir.mkdir(parents=True)
    report_dir.mkdir(parents=True)
    write_provider_ledger(run_dir / "provider_runs.jsonl", [{"provider": "DataFetcherManager", "success": True}])
    write_evidence_ledger(
        run_dir / "evidence_ledger.jsonl",
        [
            {
                "id": "price",
                "domain": "price",
                "metric": "price_history_comparison",
                "as_of": run_date,
                "fetched_at": f"{run_date}T12:00:00Z",
                "provider": "DataFetcherManager",
                "raw_path": "run_status/example.jsonl",
                "fact_type": "derived_fact",
            },
            {
                "id": "universe",
                "domain": "price",
                "metric": "universe_price_comparison",
                "as_of": run_date,
                "provider": "DataFetcherManager",
                "raw_path": "run_status/example.jsonl",
                "fact_type": "derived_fact",
            },
            {
                "id": "macro",
                "domain": "macro",
                "metric": "DGS10_history_comparison",
                "as_of": run_date,
                "provider": "FRED",
                "source_url": "https://fred.stlouisfed.org/series/DGS10",
                "fact_type": "derived_fact",
            },
        ],
    )
    (report_dir / f"{run_date}.artifact.json").write_text(
        json.dumps({"readerV3": {"timing": {
            "dataAsOf": run_date,
            "generatedAt": f"{run_date}T09:00:00Z",
        }}}),
        encoding="utf-8",
    )

    result = audit_data_temporality(docs, run_date)

    assert result["ok"] is False
    assert result["futureEvidenceCount"] == 1
