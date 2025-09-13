from __future__ import annotations

import pandas as pd

from portfolio_exporter.core import io


def run(fmt: str = "csv", return_dict: bool = False):
    """Generate simple risk metrics and optionally return them."""

    metrics = {"net_liq": 0.0, "delta": 0.0}
    if return_dict:
        return metrics
    df = pd.DataFrame([metrics])
    io.save(df, "risk_metrics", fmt)
