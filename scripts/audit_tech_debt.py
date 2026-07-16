#!/usr/bin/env python3
"""Local technical-debt audit for invest-system.

This script is read-only. It scans source size, complex Python definitions,
import cycles, dirty status classes, public legacy exposure, and reader leaks.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXCLUDE = {
    ".git",
    ".venv",
    ".venv311",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    "coverage",
    ".next",
    "logs",
    ".local_archive",
}
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".jsx"}
SCAN_DIRS = ["src", "api", "data_provider", "bot", "scripts", "apps/dsa-web/src", "apps/dsa-desktop/src", "tests"]
FORBIDDEN_READER_FIELDS = [
    "sourceHealthV2",
    "providerMatrix",
    "RAW_AGENT",
    "DERIVED_FROM_ARTIFACT",
    "claimPolicy",
    "artifactId",
    "errorType",
    "fallbackTo",
    "recordCount",
]


def run_git(args: list[str]) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return ""


def iter_code_files() -> list[Path]:
    out: list[Path] = []
    for directory in SCAN_DIRS:
        base = ROOT / directory
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix not in CODE_EXTS:
                continue
            if any(part in EXCLUDE for part in path.relative_to(ROOT).parts):
                continue
            out.append(path)
    return out


def dirty_class(path: str) -> str:
    if path.startswith(("docs/reports/", "docs/daily/", "docs/agent_memos/", "docs/market_cycle/", "docs/run_status/", "docs/official_events/", "docs/market_heat/", "docs/local_acceptance/")) or path.startswith("docs/report_") or path in {"docs/index.html", "docs/governed_results.json"}:
        return "generated/report artifacts"
    if path.startswith("docs/invest-brain/"):
        return "legacy public deletion"
    if path.startswith("docs/"):
        return "docs/source docs"
    if path.startswith("tests/"):
        return "tests"
    if path.startswith("apps/dsa-web/"):
        return "web reader"
    if path.startswith(("src/source_health/", "src/macro/")) or path in {"src/market_cycle.py", "src/report_artifact.py", "src/report_view_model.py", "src/render_report_html.py", "src/render_homepage.py", "src/pages_publication.py", "src/report_markdown.py", "src/report_policy.py", "src/core/run_context.py"}:
        return "report/source-health pipeline"
    if path.startswith("scripts/"):
        return "scripts/gates"
    if path.startswith(("src/", "data_provider/", "api/", "bot/")):
        return "backend core"
    if path.startswith(("architecture_audit/", "research_")):
        return "local audit scratch"
    return "repo metadata/root docs"


def scan_import_cycles(py_files: list[Path]) -> list[list[str]]:
    module_map: dict[Path, str] = {}
    for path in py_files:
        rel = path.relative_to(ROOT).with_suffix("").as_posix()
        module = rel.replace("/", ".")
        if module.endswith(".__init__"):
            module = module[:-9]
        module_map[path] = module
    modules = set(module_map.values())
    edge: dict[str, set[str]] = defaultdict(set)
    for path, module in module_map.items():
        try:
            tree = ast.parse(path.read_text(errors="ignore"), filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            targets: list[str] = []
            if isinstance(node, ast.Import):
                targets = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                targets = [node.module]
            for target in targets:
                matches = [
                    candidate
                    for candidate in modules
                    if candidate == target or candidate.startswith(target + ".") or target.startswith(candidate + ".")
                ]
                if not matches:
                    continue
                candidate = sorted(matches, key=len, reverse=True)[0]
                if candidate != module and candidate.split(".")[0] in {"src", "api", "data_provider", "bot", "scripts"}:
                    edge[module].add(candidate)
    index = 0
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    cycles: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for nxt in edge.get(node, set()):
            if nxt not in indices:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on_stack:
                low[node] = min(low[node], indices[nxt])
        if low[node] == indices[node]:
            comp: list[str] = []
            while True:
                item = stack.pop()
                on_stack.remove(item)
                comp.append(item)
                if item == node:
                    break
            if len(comp) > 1:
                cycles.append(sorted(comp))

    for module in sorted(modules):
        if module not in indices and module.split(".")[0] in {"src", "api", "data_provider", "bot", "scripts"}:
            visit(module)
    return cycles


def scan() -> dict[str, Any]:
    files = iter_code_files()
    stats: list[tuple[str, str, int]] = []
    large_files: list[tuple[str, int]] = []
    complex_defs: list[tuple[str, int, str, str, int, int]] = []
    py_files: list[Path] = []
    todos: list[tuple[str, int, str]] = []
    for path in files:
        text = path.read_text(errors="ignore")
        rel = path.relative_to(ROOT).as_posix()
        lines = text.splitlines()
        stats.append((rel, path.suffix, len(lines)))
        if len(lines) >= 500:
            large_files.append((rel, len(lines)))
        for lineno, line in enumerate(lines, 1):
            if re.search(r"\b(TODO|FIXME|HACK|XXX|临时|待补|后续|pending)\b", line, re.I):
                todos.append((rel, lineno, line.strip()[:180]))
        if path.suffix == ".py":
            py_files.append(path)
            try:
                tree = ast.parse(text, filename=rel)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    end = getattr(node, "end_lineno", None) or node.lineno
                    length = end - node.lineno + 1
                    branch = sum(isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.Match, ast.BoolOp, ast.IfExp, ast.ExceptHandler, ast.comprehension)) for n in ast.walk(node))
                    if length >= 80 or branch >= 18:
                        complex_defs.append((rel, node.lineno, type(node).__name__, node.name, length, branch))

    dirty_lines = [
        line
        for line in run_git(["status", "--short", "--untracked-files=all"]).splitlines()
        if line.strip()
    ]
    dirty_counts: Counter[str] = Counter()
    for line in dirty_lines:
        path = line[3:] if len(line) > 3 else line
        dirty_counts[dirty_class(path)] += 1

    legacy_public_files = [str(path.relative_to(ROOT)) for path in (ROOT / "docs" / "invest-brain").rglob("*") if path.is_file()] if (ROOT / "docs" / "invest-brain").exists() else []
    reports_dir = ROOT / "docs" / "reports"
    reader_files = sorted(reports_dir.glob("*.html")) if reports_dir.exists() else []
    reader_files += sorted((ROOT / "docs").glob("report_*.html"))
    reader_files = [path for path in reader_files if not path.name.endswith(".diagnostics.html")]
    reader_leaks: dict[str, list[str]] = {}
    for path in reader_files:
        if not path.exists():
            continue
        text = path.read_text(errors="ignore")
        found = [field for field in FORBIDDEN_READER_FIELDS if field in text]
        if found:
            reader_leaks[str(path.relative_to(ROOT))] = found

    cycles = scan_import_cycles(py_files)
    return {
        "summary": {
            "filesScanned": len(files),
            "locTotal": sum(row[2] for row in stats),
            "largeFilesGe500": len(large_files),
            "complexDefs": len(complex_defs),
            "todoHits": len(todos),
            "importCycles": len(cycles),
            "dirtyEntries": len(dirty_lines),
            "dirtyClasses": dict(dirty_counts),
            "diffShortstat": run_git(["diff", "--shortstat"]).strip(),
            "legacyPublicFiles": len(legacy_public_files),
            "readerLeakFiles": reader_leaks,
        },
        "topLargeFiles": sorted(large_files, key=lambda row: row[1], reverse=True)[:40],
        "topComplexDefs": sorted(complex_defs, key=lambda row: (row[5], row[4]), reverse=True)[:40],
        "cyclesSample": cycles[:20],
        "todoSamples": todos[:80],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit local technical debt")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("--output", help="Write JSON to path")
    args = parser.parse_args()
    payload = scan()
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
