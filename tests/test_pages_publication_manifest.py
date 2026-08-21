import os
from pathlib import Path

import pytest


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
    files.extend(
        f"reports/{run_date}/{slug}.html"
        for slug in (
            "macro", "geo", "market", "sectors", "candidates",
            "news", "stocks", "portfolio", "risk",
        )
    )
    for rel in files:
        path = runtime / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel, encoding="utf-8")

    staged = stage_pages_bundle(runtime, staging, run_date, governed_rows=[{"symbol": "AAPL"}])
    published = publish_pages_bundle(staging, docs, run_date, governed_rows=[{"symbol": "AAPL"}])

    assert f"agent_memos/{run_date}/market/04_candidate_review.json" not in staged["copied"]
    assert f"market_cycle/{run_date}/01_macro_review.json" not in staged["copied"]
    assert f"official_events/{run_date}.json" not in staged["copied"]
    assert f"reports/{run_date}.artifact.json" not in staged["copied"]
    assert f"reports/{run_date}.html" in published["copied"]
    assert not (docs / f"agent_memos/{run_date}/market/04_candidate_review.json").exists()
    assert not (docs / f"reports/{run_date}.artifact.json").exists()
    assert (docs / f"reports/{run_date}/macro.html").exists()


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


def test_public_manifest_contains_reader_only_assets(tmp_path):
    from src.pages_publication import build_pages_publication_manifest

    run_date = "2099-01-02"
    docs = tmp_path / "docs"
    manifest = build_pages_publication_manifest(docs, run_date)
    public_paths = {path.relative_to(docs).as_posix() for path in manifest.public_files()}

    assert "index.html" in public_paths
    assert f"reports/{run_date}.html" in public_paths
    assert f"reports/{run_date}/macro.html" in public_paths
    assert f"reports/{run_date}.artifact.json" not in public_paths
    assert f"reports/{run_date}.diagnostics.html" not in public_paths
    assert not any(path.startswith("run_status/") for path in public_paths)
    assert not any(path.startswith("agent_memos/") for path in public_paths)


def test_stage_pages_bundle_recreates_dirty_target_before_copy(tmp_path):
    from src.pages_publication import stage_pages_bundle

    run_date = "2099-01-02"
    source = tmp_path / "source"
    target = tmp_path / "target"
    for rel in ("index.html", f"reports/{run_date}.html"):
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("reader", encoding="utf-8")
    stale = target / f"reports/{run_date}.artifact.json"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("raw", encoding="utf-8")
    (target / ".pages_staging").write_text(run_date + "\n", encoding="utf-8")

    stage_pages_bundle(source, target, run_date)

    assert (target / "index.html").exists()
    assert not stale.exists()


@pytest.mark.parametrize(
    "run_date",
    ["../../outside", "20990102", "2099-1-2", "2099-02-30", " 2099-01-02"],
)
def test_pages_manifest_rejects_noncanonical_or_invalid_dates(tmp_path, run_date):
    from src.pages_publication import build_pages_publication_manifest

    with pytest.raises(ValueError, match="run_date"):
        build_pages_publication_manifest(tmp_path, run_date)


def test_invalid_date_cannot_escape_staging_or_delete_existing_target(tmp_path):
    from src.pages_publication import stage_pages_bundle

    source = tmp_path / "source"
    target = tmp_path / "target"
    outside = tmp_path / "outside.html"
    source.mkdir()
    target.mkdir()
    (target / ".pages_staging").write_text("2099-01-02\n", encoding="utf-8")
    protected = target / "keep.txt"
    protected.write_text("keep", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")

    with pytest.raises(ValueError, match="run_date"):
        stage_pages_bundle(source, target, "../../outside")

    assert protected.read_text(encoding="utf-8") == "keep"
    assert outside.read_text(encoding="utf-8") == "outside"


def test_stage_refuses_to_clean_existing_unmarked_directory(tmp_path):
    from src.pages_publication import stage_pages_bundle

    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    target.mkdir()
    protected = target / "keep.txt"
    protected.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="unmarked staging"):
        stage_pages_bundle(source, target, "2099-01-02")

    assert protected.read_text(encoding="utf-8") == "keep"


def test_stage_rejects_same_or_overlapping_source_and_target(tmp_path):
    from src.pages_publication import stage_pages_bundle

    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(ValueError, match="must not overlap"):
        stage_pages_bundle(source, source, "2099-01-02")
    with pytest.raises(ValueError, match="must not overlap"):
        stage_pages_bundle(source, source / "nested", "2099-01-02")


def test_stage_rejects_filesystem_root_target(tmp_path):
    from src.pages_publication import stage_pages_bundle

    source = tmp_path / "source"
    source.mkdir()

    with pytest.raises(ValueError, match="filesystem root"):
        stage_pages_bundle(source, Path(source.anchor), "2099-01-02")


def test_stage_rejects_symlink_target_without_touching_destination(tmp_path):
    from src.pages_publication import stage_pages_bundle

    source = tmp_path / "source"
    actual_target = tmp_path / "actual-target"
    source.mkdir()
    actual_target.mkdir()
    (actual_target / ".pages_staging").write_text("2099-01-02\n", encoding="utf-8")
    protected = actual_target / "keep.txt"
    protected.write_text("keep", encoding="utf-8")
    linked_target = tmp_path / "linked-target"
    os.symlink(actual_target, linked_target)

    with pytest.raises(ValueError, match="symlink"):
        stage_pages_bundle(source, linked_target, "2099-01-02")

    assert protected.read_text(encoding="utf-8") == "keep"


def test_publish_rejects_source_asset_symlink_outside_bundle(tmp_path):
    from src.pages_publication import publish_pages_bundle

    run_date = "2099-01-02"
    source = tmp_path / "source"
    target = tmp_path / "target"
    outside = tmp_path / "outside.html"
    outside.write_text("secret", encoding="utf-8")
    (source / "reports").mkdir(parents=True)
    os.symlink(outside, source / "index.html")

    with pytest.raises(ValueError, match="symlink|escapes"):
        publish_pages_bundle(source, target, run_date)

    assert not target.exists()
