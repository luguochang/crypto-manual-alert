from __future__ import annotations

from langfuse import Langfuse


def langfuse_trace_id_for_product_run(product_run_id: str) -> str:
    """Return the official deterministic Langfuse trace ID for a Product Run."""
    stable_run_id = product_run_id.strip()
    if not stable_run_id:
        raise ValueError("product_run_id is required for Langfuse trace correlation")
    if len(stable_run_id) > 255:
        raise ValueError("product_run_id is too long for Langfuse trace correlation")
    return Langfuse.create_trace_id(seed=f"crypto-alert-v2:product-run:{stable_run_id}")


__all__ = ["langfuse_trace_id_for_product_run"]
