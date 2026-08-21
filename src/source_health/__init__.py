"""Source health v2 helpers.

The package is intentionally lightweight: it derives product-facing data
confidence from existing diagnostics and artifacts without changing the
ReportArtifact v1 wire contract.
"""

from .policy import build_source_health_v2
from .run_matrix import build_snapshot_refs, load_run_matrix, validate_snapshot_chain, write_run_matrix

__all__ = [
    "build_source_health_v2",
    "build_snapshot_refs",
    "load_run_matrix",
    "validate_snapshot_chain",
    "write_run_matrix",
]
