def test_stage_and_publish_pages_bundle_copies_public_runtime_paths(tmp_path):
    from src.pages_publication import publish_pages_bundle, stage_pages_bundle

    run_date = "2099-01-02"
    compact = "20990102"
    runtime = tmp_path / "runtime"
    staging = tmp_path / "staging"
    docs = tmp_path / "docs"
    files = [
        "index.html",
        f"reports/{run_date}.html",
        f"reports/{run_date}.artifact.json",
        f"daily/{run_date}.md",
        f"daily/{run_date}.html",
        f"agent_memos/{run_date}/index.html",
        f"agent_memos/{run_date}/market/04_candidate_review.json",
        f"market_cycle/{run_date}/summary.html",
        f"market_cycle/{run_date}/00_one_screen_brief.html",
        f"market_cycle/{run_date}/01_macro_review.html",
        f"market_cycle/{run_date}/01_macro_review.json",
        f"market_cycle/{run_date}/09_screening_funnel.html",
        f"market_cycle/{run_date}/11_deep_review_queue.html",
        f"market_cycle/{run_date}/13_source_health.html",
        f"market_cycle/{run_date}/14_market_strategy.html",
        f"official_events/{run_date}.json",
        f"report_{compact}.md",
        f"report_{compact}.html",
        "governed_results.json",
    ]
    for rel in files:
        path = runtime / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel, encoding="utf-8")

    staged = stage_pages_bundle(runtime, staging, run_date, governed_rows=[{"symbol": "AAPL"}])
    published = publish_pages_bundle(staging, docs, run_date, governed_rows=[{"symbol": "AAPL"}])

    assert f"agent_memos/{run_date}/market/04_candidate_review.json" in staged["copied"]
    assert f"market_cycle/{run_date}/01_macro_review.json" in staged["copied"]
    assert f"official_events/{run_date}.json" in staged["copied"]
    assert (staging / f"reports/{run_date}.artifact.json").read_text(encoding="utf-8") == f"reports/{run_date}.artifact.json"
    assert f"reports/{run_date}.html" in published["copied"]
    assert (docs / f"agent_memos/{run_date}/market/04_candidate_review.json").exists()


def test_reader_manifest_excludes_diagnostics_compat_pages(tmp_path):
    from src.pages_publication import build_pages_publication_manifest

    run_date = "2099-01-02"
    docs = tmp_path / "docs"
    for rel in (
        f"reports/{run_date}.html",
        f"market_cycle/{run_date}/13_source_health.html",
        f"market_cycle/{run_date}/14_market_strategy.html",
    ):
        path = docs / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel, encoding="utf-8")

    manifest = build_pages_publication_manifest(docs, run_date)
    reader_paths = {path.relative_to(docs).as_posix() for path in manifest.reader_html()}
    entry_paths = {path.relative_to(docs).as_posix() for path in manifest.entry_html()}

    assert f"reports/{run_date}.html" in reader_paths
    assert f"market_cycle/{run_date}/13_source_health.html" not in reader_paths
    assert f"market_cycle/{run_date}/14_market_strategy.html" not in reader_paths
    assert f"market_cycle/{run_date}/13_source_health.html" in entry_paths
