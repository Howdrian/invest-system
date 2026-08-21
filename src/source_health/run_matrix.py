"""Run matrix and snapshot-chain helpers for local report publication."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Sequence

from .smoke_symbols import full_review_smoke_symbols

RUN_MATRIX_SCHEMA = "run_matrix_v1"


def sha256_file(path: str | Path) -> str | None:
    source = Path(path)
    if not source.exists() or not source.is_file():
        return None
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run_status_dir(docs_dir: str | Path, run_date: str) -> Path:
    return Path(docs_dir) / "run_status" / run_date


def run_matrix_path(docs_dir: str | Path, run_date: str) -> Path:
    return run_status_dir(docs_dir, run_date) / "run_matrix.json"


def default_run_id(run_date: str, git_sha: str | None = None) -> str:
    short = (git_sha or "local")[:12]
    return f"local-{run_date}-{short}"


def current_git_sha(cwd: str | Path | None = None) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd or Path.cwd()),
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "unknown"


def load_run_matrix(docs_dir: str | Path, run_date: str) -> Dict[str, Any]:
    path = run_matrix_path(docs_dir, run_date)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def write_run_matrix(
    docs_dir: str | Path,
    run_date: str,
    *,
    symbols: Sequence[str] | None = None,
    stages: Iterable[Mapping[str, Any]] | None = None,
    git_sha: str | None = None,
    run_id: str | None = None,
) -> Dict[str, Any]:
    docs = Path(docs_dir)
    sha = git_sha or current_git_sha(docs.parent if docs.name == "docs" else Path.cwd())
    payload: Dict[str, Any] = {
        "schema": RUN_MATRIX_SCHEMA,
        "runId": run_id or default_run_id(run_date, sha),
        "runDate": run_date,
        "gitSha": sha,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "symbols": _dedupe_symbols(symbols or _symbols_from_docs(docs, run_date) or full_review_smoke_symbols()),
        "stages": [],
    }
    for stage in stages or []:
        payload["stages"].append(_stage_row(stage))
    path = run_matrix_path(docs, run_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def upsert_run_matrix_stage(
    docs_dir: str | Path,
    run_date: str,
    stage: Mapping[str, Any],
    *,
    symbols: Sequence[str] | None = None,
) -> Dict[str, Any]:
    current = load_run_matrix(docs_dir, run_date)
    existing = [row for row in current.get("stages", []) if isinstance(row, Mapping)]
    name = str(stage.get("name") or "stage")
    rows = [row for row in existing if str(row.get("name") or "") != name]
    rows.append(_stage_row(stage))
    return write_run_matrix(
        docs_dir,
        run_date,
        symbols=symbols or current.get("symbols") or None,
        stages=rows,
        git_sha=current.get("gitSha") or None,
        run_id=current.get("runId") or None,
    )


def build_snapshot_refs(docs_dir: str | Path, run_date: str, *, agent_run_id: str | None = None) -> Dict[str, Any]:
    docs = Path(docs_dir)
    refs = {
        "providerLedgerPath": f"run_status/{run_date}/provider_runs.jsonl",
        "evidenceLedgerPath": f"run_status/{run_date}/evidence_ledger.jsonl",
        "sourceHealthPath": f"run_status/{run_date}/source_health_v2.json",
        "runMatrixPath": f"run_status/{run_date}/run_matrix.json",
        "providerLedgerSha256": sha256_file(docs / "run_status" / run_date / "provider_runs.jsonl"),
        "evidenceLedgerSha256": sha256_file(docs / "run_status" / run_date / "evidence_ledger.jsonl"),
        "sourceHealthSha256": sha256_file(docs / "run_status" / run_date / "source_health_v2.json"),
        "runMatrixSha256": sha256_file(docs / "run_status" / run_date / "run_matrix.json"),
        "agentRunId": agent_run_id or _agent_run_id(docs, run_date),
    }
    return {key: value for key, value in refs.items() if value not in (None, "")}


def validate_snapshot_chain(docs_dir: str | Path, artifact: Mapping[str, Any]) -> list[str]:
    docs = Path(docs_dir)
    errors: list[str] = []
    run_date = str(artifact.get("runDate") or "")
    refs = artifact.get("snapshotRefs") if isinstance(artifact.get("snapshotRefs"), Mapping) else {}
    run_matrix = artifact.get("runMatrix") if isinstance(artifact.get("runMatrix"), Mapping) else {}
    if not run_date:
        return ["artifact runDate missing"]
    if run_matrix:
        matrix_date = str(run_matrix.get("runDate") or "")
        if matrix_date and matrix_date != run_date:
            errors.append(f"runMatrix.runDate mismatch: {matrix_date} != {run_date}")
    else:
        errors.append("artifact missing runMatrix")
    if not refs:
        errors.append("artifact missing snapshotRefs")
        return errors

    path_keys = {
        "providerLedgerSha256": refs.get("providerLedgerPath") or f"run_status/{run_date}/provider_runs.jsonl",
        "evidenceLedgerSha256": refs.get("evidenceLedgerPath") or f"run_status/{run_date}/evidence_ledger.jsonl",
        "sourceHealthSha256": refs.get("sourceHealthPath") or f"run_status/{run_date}/source_health_v2.json",
        "runMatrixSha256": refs.get("runMatrixPath") or f"run_status/{run_date}/run_matrix.json",
    }
    for hash_key, rel in path_keys.items():
        expected = refs.get(hash_key)
        path = docs / str(rel)
        actual = sha256_file(path)
        if expected and actual and expected != actual:
            errors.append(f"{hash_key} mismatch")
        elif expected and actual is None:
            errors.append(f"{hash_key} source missing: {rel}")

    source_health = _read_json(docs / f"run_status/{run_date}/source_health_v2.json")
    if isinstance(source_health, Mapping):
        source_mode = str(source_health.get("overallMode") or "")
        artifact_mode = str(artifact.get("analysisMode") or (artifact.get("sourceHealthV2") or {}).get("overallMode") or "")
        if source_mode and artifact_mode and source_mode != artifact_mode:
            errors.append(f"sourceHealth mode mismatch: {source_mode} != {artifact_mode}")
    return errors


def _stage_row(stage: Mapping[str, Any]) -> Dict[str, Any]:
    row = {
        "name": str(stage.get("name") or "stage"),
        "status": str(stage.get("status") or "skipped"),
        "blocking": bool(stage.get("blocking", False)),
        "inputs": list(stage.get("inputs") or []),
        "outputs": list(stage.get("outputs") or []),
        "errorType": stage.get("errorType"),
        "sha256": stage.get("sha256"),
    }
    return {key: value for key, value in row.items() if value not in (None, "", [])}


def _symbols_from_docs(docs: Path, run_date: str) -> list[str]:
    out: list[str] = []
    official = _read_json(docs / "official_events" / f"{run_date}.json")
    if isinstance(official, Mapping):
        out.extend(str(item) for item in official.get("symbols") or [] if str(item).strip())
    governed = _read_json(docs / "governed_results.json")
    if isinstance(governed, list):
        for row in governed:
            if isinstance(row, Mapping) and str(row.get("run_date") or run_date) == run_date:
                symbol = str(row.get("code") or row.get("symbol") or "").strip()
                if symbol:
                    out.append(symbol)
    return _dedupe_symbols(out)


def _dedupe_symbols(symbols: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        text = str(symbol).strip()
        if not text:
            continue
        key = text.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _agent_run_id(docs: Path, run_date: str) -> str:
    matrix = load_run_matrix(docs, run_date)
    if matrix.get("runId"):
        return str(matrix["runId"])
    return default_run_id(run_date)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
