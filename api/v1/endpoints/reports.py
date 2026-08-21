# -*- coding: utf-8 -*-
"""Unified report-artifact API.

These endpoints expose ReportArtifact v1.  Static daily artifacts in
``docs/reports/*.artifact.json`` are preferred; persisted history records are
kept as a fallback for older reports and stock-level detail views.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from api.deps import get_database_manager
from api.v1.schemas.common import ErrorResponse
from src.report_artifact import build_stock_artifact_from_history_detail, validate_report_artifact
from src.services.history_service import HistoryService
from src.storage import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REPORTS_DIR = REPO_ROOT / "docs" / "reports"


@router.get(
    "/latest",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "最新 ReportArtifact"},
        404: {"description": "暂无报告", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取最新统一报告 artifact",
)
def get_latest_report_artifact(
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> Dict[str, Any]:
    """Return the newest persisted report as ReportArtifact v1."""

    artifacts = _load_report_artifacts(db_manager, limit=1)
    if not artifacts:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": "暂无可用报告 artifact"},
        )
    return artifacts[0]


@router.get(
    "/artifacts",
    response_model=List[Dict[str, Any]],
    responses={500: {"description": "服务器错误", "model": ErrorResponse}},
    summary="列出统一报告 artifacts",
)
def list_report_artifacts(
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> List[Dict[str, Any]]:
    """List recent persisted reports as ReportArtifact v1 payloads."""

    return _load_report_artifacts(db_manager, limit=limit)


@router.get(
    "/artifacts/{artifact_id}",
    response_model=Dict[str, Any],
    responses={
        200: {"description": "ReportArtifact 详情"},
        404: {"description": "报告不存在", "model": ErrorResponse},
        500: {"description": "服务器错误", "model": ErrorResponse},
    },
    summary="获取统一报告 artifact 详情",
)
def get_report_artifact(
    artifact_id: str,
    db_manager: DatabaseManager = Depends(get_database_manager),
) -> Dict[str, Any]:
    """Get a single artifact by ``history:<id>`` or raw history id."""

    file_artifact = _load_file_report_artifact_by_id(artifact_id)
    if file_artifact is not None:
        return file_artifact

    record_id = _artifact_id_to_record_id(artifact_id)
    service = HistoryService(db_manager)
    detail = service.resolve_and_get_detail(record_id)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "message": f"未找到 artifact={artifact_id}"},
        )
    return build_stock_artifact_from_history_detail(detail)


def _load_report_artifacts(db_manager: DatabaseManager, *, limit: int) -> List[Dict[str, Any]]:
    file_artifacts = _load_file_report_artifacts(limit=limit)
    if len(file_artifacts) >= limit:
        return file_artifacts[:limit]

    service = HistoryService(db_manager)
    result = service.get_history_list(page=1, limit=limit - len(file_artifacts))
    artifacts: List[Dict[str, Any]] = list(file_artifacts)
    for item in result.get("items", []):
        record_id = item.get("id") or item.get("query_id")
        if record_id is None:
            continue
        detail = service.resolve_and_get_detail(str(record_id))
        if detail is None:
            continue
        artifacts.append(build_stock_artifact_from_history_detail(detail))
    return artifacts


def _resolve_reports_dir(reports_dir: Path | None = None) -> Path:
    if reports_dir is not None:
        return reports_dir
    cwd_reports = Path.cwd() / "docs" / "reports"
    return cwd_reports if cwd_reports.exists() else DEFAULT_REPORTS_DIR


def _load_file_report_artifacts(*, limit: int, reports_dir: Path | None = None) -> List[Dict[str, Any]]:
    reports_dir = _resolve_reports_dir(reports_dir)
    if not reports_dir.exists():
        return []
    artifacts: List[Dict[str, Any]] = []
    for path in sorted(reports_dir.glob("*.artifact.json"), reverse=True):
        artifact = _read_file_artifact(path)
        if artifact is not None:
            artifacts.append(artifact)
        if len(artifacts) >= limit:
            break
    artifacts.sort(key=lambda item: (str(item.get("runDate") or ""), str(item.get("generatedAt") or "")), reverse=True)
    return artifacts[:limit]


def _load_file_report_artifact_by_id(artifact_id: str, reports_dir: Path | None = None) -> Dict[str, Any] | None:
    reports_dir = _resolve_reports_dir(reports_dir)
    value = str(artifact_id or "").strip()
    if not value or not reports_dir.exists():
        return None
    artifact_date = _daily_artifact_date(value)
    candidates = [reports_dir / f"{artifact_date}.artifact.json"] if artifact_date else []
    for candidate in candidates:
        artifact = _read_file_artifact(candidate)
        if artifact is not None:
            return artifact
    for path in reports_dir.glob("*.artifact.json"):
        artifact = _read_file_artifact(path)
        if artifact is not None and str(artifact.get("artifactId") or "") == value:
            return artifact
    return None


def _daily_artifact_date(artifact_id: str) -> str | None:
    """Return a canonical daily date without allowing path-like identifiers."""

    value = str(artifact_id or "").strip()
    if value.startswith("daily:"):
        value = value.split(":", 1)[1]
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return value if parsed.isoformat() == value else None


def _read_file_artifact(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read report artifact %s: %s", path, exc)
        return None
    if not isinstance(payload, dict):
        return None
    ok, errors = validate_report_artifact(payload)
    if not ok:
        logger.warning("Invalid report artifact %s: %s", path, errors)
        return None
    return payload


def _artifact_id_to_record_id(artifact_id: str) -> str:
    value = str(artifact_id or "").strip()
    if value.startswith("history:"):
        return value.split(":", 1)[1]
    if value.startswith("query:"):
        return value.split(":", 1)[1]
    return value
