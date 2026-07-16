"""Static Pages publication manifest.

One pure manifest defines the files that make a daily bundle public.  Renderers
and validators can share it instead of each guessing required paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Iterable, List


@dataclass(frozen=True)
class PagesPublicationManifest:
    docs_dir: Path
    run_date: str
    has_governed_rows: bool = False

    @property
    def compact_date(self) -> str:
        return self.run_date.replace("-", "")

    def required_files(self) -> List[Path]:
        files = [
            self.docs_dir / "index.html",
            self.docs_dir / "reports" / f"{self.run_date}.html",
            self.docs_dir / "reports" / f"{self.run_date}.artifact.json",
            self.docs_dir / "reports" / f"{self.run_date}.diagnostics.html",
            self.docs_dir / "reports" / self.run_date / "macro.html",
            self.docs_dir / "reports" / self.run_date / "geo.html",
            self.docs_dir / "reports" / self.run_date / "market.html",
            self.docs_dir / "reports" / self.run_date / "news.html",
            self.docs_dir / "reports" / self.run_date / "stocks.html",
            self.docs_dir / "reports" / self.run_date / "portfolio.html",
            self.docs_dir / "reports" / self.run_date / "risk.html",
            self.docs_dir / "daily" / f"{self.run_date}.md",
            self.docs_dir / "daily" / f"{self.run_date}.html",
            self.docs_dir / "agent_memos" / self.run_date / "index.html",
            self.docs_dir / "market_cycle" / self.run_date / "summary.html",
            self.docs_dir / "market_cycle" / self.run_date / "00_one_screen_brief.html",
            self.docs_dir / "market_cycle" / self.run_date / "01_macro_review.html",
            self.docs_dir / "market_cycle" / self.run_date / "09_screening_funnel.html",
            self.docs_dir / "market_cycle" / self.run_date / "11_deep_review_queue.html",
            self.docs_dir / "market_cycle" / self.run_date / "13_source_health.html",
            self.docs_dir / "market_cycle" / self.run_date / "14_market_strategy.html",
        ]
        if self.has_governed_rows:
            files.extend([
                self.docs_dir / f"report_{self.compact_date}.md",
                self.docs_dir / f"report_{self.compact_date}.html",
                self.docs_dir / "governed_results.json",
            ])
        return files

    def entry_html(self) -> Iterable[Path]:
        candidates = [
            self.docs_dir / "index.html",
            self.docs_dir / "reports" / f"{self.run_date}.html",
            self.docs_dir / "reports" / f"{self.run_date}.diagnostics.html",
            self.docs_dir / "reports" / self.run_date / "macro.html",
            self.docs_dir / "reports" / self.run_date / "geo.html",
            self.docs_dir / "reports" / self.run_date / "market.html",
            self.docs_dir / "reports" / self.run_date / "news.html",
            self.docs_dir / "reports" / self.run_date / "stocks.html",
            self.docs_dir / "reports" / self.run_date / "portfolio.html",
            self.docs_dir / "reports" / self.run_date / "risk.html",
            self.docs_dir / "daily" / f"{self.run_date}.html",
            self.docs_dir / "agent_memos" / self.run_date / "index.html",
            self.docs_dir / "market_cycle" / self.run_date / "00_one_screen_brief.html",
            self.docs_dir / "market_cycle" / self.run_date / "01_macro_review.html",
            self.docs_dir / "market_cycle" / self.run_date / "09_screening_funnel.html",
            self.docs_dir / "market_cycle" / self.run_date / "11_deep_review_queue.html",
            self.docs_dir / "market_cycle" / self.run_date / "13_source_health.html",
            self.docs_dir / "market_cycle" / self.run_date / "14_market_strategy.html",
        ]
        if self.has_governed_rows:
            candidates.append(self.docs_dir / f"report_{self.compact_date}.html")
        return _existing_unique(candidates)

    def reader_html(self) -> Iterable[Path]:
        candidates = [
            self.docs_dir / "index.html",
            self.docs_dir / "reports" / f"{self.run_date}.html",
            self.docs_dir / "reports" / self.run_date / "macro.html",
            self.docs_dir / "reports" / self.run_date / "geo.html",
            self.docs_dir / "reports" / self.run_date / "market.html",
            self.docs_dir / "reports" / self.run_date / "news.html",
            self.docs_dir / "reports" / self.run_date / "stocks.html",
            self.docs_dir / "reports" / self.run_date / "portfolio.html",
            self.docs_dir / "reports" / self.run_date / "risk.html",
            self.docs_dir / "daily" / f"{self.run_date}.html",
            self.docs_dir / "market_cycle" / self.run_date / "00_one_screen_brief.html",
            self.docs_dir / "market_cycle" / self.run_date / "01_macro_review.html",
            self.docs_dir / "market_cycle" / self.run_date / "09_screening_funnel.html",
            self.docs_dir / "market_cycle" / self.run_date / "11_deep_review_queue.html",
        ]
        if self.has_governed_rows:
            candidates.append(self.docs_dir / f"report_{self.compact_date}.html")
        return _existing_unique(candidates)


def build_pages_publication_manifest(docs_dir: str | Path, run_date: str, governed_rows: list[dict] | None = None) -> PagesPublicationManifest:
    return PagesPublicationManifest(Path(docs_dir), run_date, bool(governed_rows))


def stage_pages_bundle(source_dir: str | Path, staging_dir: str | Path, run_date: str, governed_rows: list[dict] | None = None) -> dict:
    return _copy_pages_bundle(Path(source_dir), Path(staging_dir), run_date, governed_rows, ".pages_staging")


def publish_pages_bundle(staging_dir: str | Path, docs_dir: str | Path, run_date: str, governed_rows: list[dict] | None = None) -> dict:
    return _copy_pages_bundle(Path(staging_dir), Path(docs_dir), run_date, governed_rows, ".last_pages_publish")


def _copy_pages_bundle(
    source_dir: Path,
    target_dir: Path,
    run_date: str,
    governed_rows: list[dict] | None = None,
    marker_name: str = ".pages_staging",
) -> dict:
    copied: list[str] = []
    missing: list[str] = []
    for rel in _public_bundle_paths(source_dir, run_date, governed_rows):
        src = source_dir / rel
        dst = target_dir / rel
        if not src.exists() or not src.is_file():
            missing.append(rel)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel)
    marker = target_dir / marker_name
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{run_date}\n", encoding="utf-8")
    return {"schema": "pages_bundle_copy_v1", "runDate": run_date, "copied": copied, "missing": missing}


def _public_bundle_paths(source_dir: Path, run_date: str, governed_rows: list[dict] | None = None) -> list[str]:
    manifest = build_pages_publication_manifest(source_dir, run_date, governed_rows)
    paths = {path.relative_to(source_dir).as_posix() for path in manifest.required_files() if path.exists()}
    for folder in (
        source_dir / "agent_memos" / run_date,
        source_dir / "market_cycle" / run_date,
        source_dir / "market_heat",
        source_dir / "official_events",
        source_dir / "run_status" / run_date,
    ):
        if folder.exists():
            for path in folder.rglob("*"):
                if path.is_file():
                    paths.add(path.relative_to(source_dir).as_posix())
    return sorted(paths)


def _existing_unique(candidates: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for path in candidates:
        if path.exists() and path not in seen:
            seen.add(path)
            yield path
