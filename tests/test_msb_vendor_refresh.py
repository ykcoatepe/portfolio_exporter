from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

import src.psd.datasources.msb_vendor as msb_vendor


def test_msb_vendor_refresh_writes_csvs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    env = {
        "PSD_MSB_AUTO_REFRESH": "1",
        "MSB_VENDOR_TTL_HOURS": "0",
    }

    idx = pd.bdate_range("2024-01-02", periods=3)

    def _fake_download(ticker: str, period: str) -> pd.Series:
        base = 10.0 if "VX" in ticker else 100.0
        values = [base + i for i in range(len(idx))]
        return pd.Series(values, index=idx)

    monkeypatch.setattr(msb_vendor, "_download_close_series_yf", _fake_download)

    vendor_dir = tmp_path / "vendor"
    status = msb_vendor.refresh_vendor_data(vendor_dir, env=env)

    assert status["vx1"] == "refreshed"
    assert status["vx2"] == "refreshed"
    assert status["spx_ret"] == "refreshed"
    assert (vendor_dir / "vx1.csv").exists()
    assert (vendor_dir / "vx2.csv").exists()
    assert (vendor_dir / "spx_ret.csv").exists()
