"""Shared error-budget gate for loop-style assets.

Every scraper and LLM pass iterates a work list, counts per-item failures,
and reports them as metadata — which means a run where 100% of items failed
(revoked API key, changed selector, dead endpoint) still materializes green.
This gate turns a systemic failure into a failed run so alerting fires.

Per-item failures below the threshold stay non-fatal: individual dirty
records shouldn't kill a 30K-item batch.
"""

import os


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def check_error_budget(
    log,
    *,
    label: str,
    errors: int,
    total: int,
    threshold: float | None = None,
    min_total: int = 5,
) -> None:
    """Raise if ``errors / total`` exceeds the budget.

    Args:
        label: asset/pass name for the error message.
        errors: failed items this run.
        total: attempted items this run.
        threshold: max tolerated failure ratio (default 0.3, override with
            COUNTYIQ_ERROR_BUDGET).
        min_total: below this many attempts, never raise — tiny runs where
            1-2 failures dominate the ratio shouldn't hard-fail.
    """
    if total < min_total or errors == 0:
        return
    if threshold is None:
        threshold = _float_env("COUNTYIQ_ERROR_BUDGET", 0.3)
    ratio = errors / total
    if ratio > threshold:
        msg = (
            f"{label}: error budget exceeded — {errors}/{total} items failed "
            f"({ratio:.0%} > {threshold:.0%}). Failing the run so this is "
            f"visible instead of a green run full of errors."
        )
        log.error(msg)
        raise RuntimeError(msg)
    log.warning(
        f"{label}: {errors}/{total} items failed ({ratio:.0%}) — within error budget"
    )
