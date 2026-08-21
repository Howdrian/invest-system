from __future__ import annotations

import json
from datetime import timedelta, timezone


class FakeIntelligenceService:
    def __init__(self):
        self.sources = []

    def list_sources(self, **_filters):
        return {"items": list(self.sources), "total": len(self.sources)}

    def create_source_from_template(self, template_id, overrides=None):
        source = {
            "id": len(self.sources) + 1,
            "name": template_id,
            "enabled": bool((overrides or {}).get("enabled")),
            "scope_value": None,
            "market": "global",
        }
        self.sources.append(source)
        return source

    def fetch_enabled_sources(self):
        return {
            "ok": True,
            "source_count": len(self.sources),
            "results": [
                {"ok": True, "source_id": source["id"], "fetched_count": 1, "saved_count": 1}
                for source in self.sources
            ],
        }

    def list_items(self, **_filters):
        items = [
            {
                "id": 1,
                "source_name": "sec-company-news",
                "title": "SEC update",
                "summary": "Official release discovered by upstream intelligence.",
                "url": "https://www.sec.gov/news/example",
                "published_at": "2099-01-02T08:00:00Z",
                "fetched_at": "2099-01-02T08:01:00Z",
                "scope_type": "market",
                "scope_value": None,
                "market": "us",
            }
        ]
        return {"items": items, "total": len(items), "page": 1, "page_size": 100}


def test_safe_intelligence_sources_bootstrap_and_enter_daily_ledgers(tmp_path):
    from src.source_health.daily_ledgers import write_daily_source_health_ledgers
    from src.source_health.evidence_ledger import load_evidence_ledger
    from src.source_health.intelligence_evidence import SAFE_BOOTSTRAP_TEMPLATES, collect_intelligence_evidence
    from src.source_health.provider_ledger import load_provider_ledger

    docs = tmp_path / "docs"
    run_date = "2099-01-02"
    service = FakeIntelligenceService()

    summary = collect_intelligence_evidence(docs, run_date, service=service)

    assert summary["bootstrapped"] == list(SAFE_BOOTSTRAP_TEMPLATES)
    assert summary["enabledSourcesFetched"] == 3
    source_evidence = load_evidence_ledger(docs / "run_status" / run_date / "intelligence_evidence.jsonl")
    item = next(row for row in source_evidence if row["id"] == "intelligence:1")
    assert item["fact_type"] == "discovery"
    assert item["published_at"] == "2099-01-02T08:00:00Z"
    assert item["fetched_at"] == "2099-01-02T08:01:00Z"
    assert any(row.get("metric") == "intelligence_recency_comparison" for row in source_evidence)

    write_daily_source_health_ledgers(docs, run_date)
    providers = load_provider_ledger(docs / "run_status" / run_date / "provider_runs.jsonl")
    evidence = load_evidence_ledger(docs / "run_status" / run_date / "evidence_ledger.jsonl")
    assert any(row.get("provider") == "sec-company-news" for row in providers)
    assert any(row.get("id") == "intelligence:1" for row in evidence)
    matrix = json.loads((docs / "run_status" / run_date / "run_matrix.json").read_text(encoding="utf-8"))
    assert any(row.get("name") == "intelligence_evidence_collection" and row.get("status") == "success" for row in matrix["stages"])


def test_naive_local_fetch_timestamp_is_normalized_to_utc():
    from src.source_health.temporal import iso_timestamp

    assert iso_timestamp(
        "2099-01-02T08:01:00",
        naive_timezone=timezone(timedelta(hours=7)),
    ) == "2099-01-02T01:01:00Z"
