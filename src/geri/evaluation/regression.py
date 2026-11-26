"""Deterministic held-out comparison for pretraining-to-SFT regressions."""
from __future__ import annotations

from .__init__ import __doc__  # keep package import explicit


def compare_regression(baseline: dict[str, float], candidate: dict[str, float], max_loss_ratio: float = 1.10) -> dict:
    if not baseline or not candidate:
        raise ValueError("baseline and candidate metrics are required")
    ratios = {name: candidate[name] / max(value, 1e-12) for name, value in baseline.items() if name in candidate}
    if not ratios:
        raise ValueError("baseline and candidate have no comparable metrics")
    return {"passed": all(ratio <= max_loss_ratio for ratio in ratios.values()), "max_loss_ratio": max_loss_ratio, "ratios": ratios}
