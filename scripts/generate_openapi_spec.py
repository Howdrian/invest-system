#!/usr/bin/env python3
"""Generate the committed OpenAPI artifact from the FastAPI application."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.app import create_app  # noqa: E402


OUTPUT_PATH = ROOT / "docs" / "architecture" / "api_spec.json"


def render_openapi_spec() -> str:
    """Return the canonical, deterministic OpenAPI artifact text."""
    return (
        json.dumps(
            create_app().openapi(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def main() -> None:
    rendered = render_openapi_spec()
    if "--check" in sys.argv[1:]:
        current = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else ""
        if current != rendered:
            raise SystemExit(
                "OpenAPI artifact is stale; run python scripts/generate_openapi_spec.py"
            )
        print(f"OpenAPI artifact is current: {OUTPUT_PATH}")
        return
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
