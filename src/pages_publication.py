"""Static Pages publication manifest.

One pure manifest defines the files that make a daily bundle public.  Renderers
and validators can share it instead of each guessing required paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import shutil
from typing import Iterable, List


_STAGING_MARKER = ".pages_staging"


def validate_pages_run_date(run_date: str) -> str:
    """Return a canonical ISO calendar date or reject unsafe date strings."""

    if not isinstance(run_date, str):
        raise ValueError("run_date must be a YYYY-MM-DD string")
    try:
        parsed = date.fromisoformat(run_date)
    except ValueError as exc:
        raise ValueError("run_date must be a valid YYYY-MM-DD date") from exc
    if parsed.isoformat() != run_date:
        raise ValueError("run_date must use canonical YYYY-MM-DD format")
    return run_date


@dataclass(frozen=True)
class PagesPublicationManifest:
    docs_dir: Path
    run_date: str
    has_governed_rows: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "docs_dir", Path(self.docs_dir))
        validate_pages_run_date(self.run_date)

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

    def public_files(self) -> List[Path]:
        """Reader-only assets safe to copy to a public static site.

        Raw artifacts, diagnostics, agent memos and run ledgers stay in the
        maintenance workspace.  They are validated before staging, but are not
        part of the public Pages bundle.
        """

        return [
            self.docs_dir / "index.html",
            self.docs_dir / "reports" / f"{self.run_date}.html",
            *[
                self.docs_dir / "reports" / self.run_date / f"{slug}.html"
                for slug in (
                    "macro", "geo", "market", "sectors", "candidates",
                    "news", "stocks", "portfolio", "risk",
                )
            ],
        ]

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

    def public_html(self) -> Iterable[Path]:
        return _existing_unique(self.public_files())


def build_pages_publication_manifest(
    docs_dir: str | Path,
    run_date: str,
    governed_rows: list[dict] | None = None,
) -> PagesPublicationManifest:
    return PagesPublicationManifest(Path(docs_dir), run_date, bool(governed_rows))


def stage_pages_bundle(
    source_dir: str | Path,
    staging_dir: str | Path,
    run_date: str,
    governed_rows: list[dict] | None = None,
) -> dict:
    validate_pages_run_date(run_date)
    source, target = _resolve_copy_roots(source_dir, staging_dir)
    # Staging is disposable build output. Recreate it so stale raw files from a
    # prior run can never become part of the uploaded Pages artifact. Never
    # delete a caller-selected directory unless a prior staging run marked it.
    if target.exists():
        marker = _safe_child(target, Path(_STAGING_MARKER), label="staging marker")
        if marker.is_symlink() or not marker.is_file():
            raise ValueError(
                f"refusing to clean unmarked staging directory: {target}"
            )
        try:
            validate_pages_run_date(marker.read_text(encoding="utf-8").strip())
        except (OSError, ValueError) as exc:
            raise ValueError(
                f"refusing to clean staging directory with invalid marker: {target}"
            ) from exc
        shutil.rmtree(target)
    return _copy_pages_bundle(source, target, run_date, governed_rows, _STAGING_MARKER)


def publish_pages_bundle(
    staging_dir: str | Path,
    docs_dir: str | Path,
    run_date: str,
    governed_rows: list[dict] | None = None,
) -> dict:
    validate_pages_run_date(run_date)
    source, target = _resolve_copy_roots(staging_dir, docs_dir)
    return _copy_pages_bundle(
        source,
        target,
        run_date,
        governed_rows,
        ".last_pages_publish",
    )


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
        rel_path = _validate_relative_path(Path(rel))
        src = _safe_child(source_dir, rel_path, label="source asset")
        dst = _safe_child(target_dir, rel_path, label="target asset")
        if not src.exists() or not src.is_file():
            missing.append(rel)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        # Re-check after directory creation so a pre-existing symlink can never
        # redirect the write outside the publication root.
        dst = _safe_child(target_dir, rel_path, label="target asset")
        shutil.copy2(src, dst)
        copied.append(rel)
    marker = _safe_child(
        target_dir,
        _validate_relative_path(Path(marker_name)),
        label="publication marker",
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(f"{run_date}\n", encoding="utf-8")
    return {"schema": "pages_bundle_copy_v1", "runDate": run_date, "copied": copied, "missing": missing}


def _public_bundle_paths(source_dir: Path, run_date: str, governed_rows: list[dict] | None = None) -> list[str]:
    manifest = build_pages_publication_manifest(source_dir, run_date, governed_rows)
    paths: list[str] = []
    for path in manifest.public_files():
        rel = _validate_relative_path(path.relative_to(source_dir))
        # Preserve missing entries so direct callers receive an auditable
        # manifest instead of silently treating an incomplete bundle as clean.
        _safe_child(source_dir, rel, label="source asset")
        paths.append(rel.as_posix())
    return sorted(paths)


def _resolve_copy_roots(
    source_dir: str | Path,
    target_dir: str | Path,
) -> tuple[Path, Path]:
    source = _resolve_safe_root(source_dir, label="source", must_exist=True)
    target = _resolve_safe_root(target_dir, label="target", must_exist=False)
    if _is_within(source, target) or _is_within(target, source):
        raise ValueError(
            f"source and target publication roots must not overlap: {source} / {target}"
        )
    return source, target


def _resolve_safe_root(
    value: str | Path,
    *,
    label: str,
    must_exist: bool,
) -> Path:
    raw = Path(value).expanduser().absolute()
    _reject_symlink_components(raw, label=label)
    resolved = raw.resolve(strict=False)
    if resolved == Path(resolved.anchor):
        raise ValueError(f"{label} publication root cannot be a filesystem root")
    if must_exist and (not resolved.exists() or not resolved.is_dir()):
        raise ValueError(f"{label} publication root is not a directory: {resolved}")
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"{label} publication root is not a directory: {resolved}")
    return resolved


def _validate_relative_path(path: Path) -> Path:
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"unsafe publication path: {path}")
    return path


def _safe_child(root: Path, rel: Path, *, label: str) -> Path:
    rel = _validate_relative_path(rel)
    candidate = root / rel
    _reject_symlink_components(candidate, label=label, stop_at=root)
    resolved = candidate.resolve(strict=False)
    if not _is_within(resolved, root):
        raise ValueError(f"{label} escapes publication root: {rel}")
    return resolved


def _reject_symlink_components(
    path: Path,
    *,
    label: str,
    stop_at: Path | None = None,
) -> None:
    current = path
    while True:
        if current.is_symlink():
            raise ValueError(f"{label} path contains a symlink: {current}")
        if stop_at is not None and current == stop_at:
            return
        if current.parent == current:
            return
        current = current.parent


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _existing_unique(candidates: Iterable[Path]) -> Iterable[Path]:
    seen: set[Path] = set()
    for path in candidates:
        if path.exists() and path not in seen:
            seen.add(path)
            yield path
