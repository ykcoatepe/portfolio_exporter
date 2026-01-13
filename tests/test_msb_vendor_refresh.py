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


def test_msb_vendor_refresh_uses_ibkr_when_available(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    env = {
        "PSD_MSB_AUTO_REFRESH": "1",
        "MSB_VENDOR_TTL_HOURS": "0",
        "MSB_SOURCE": "ibkr",
    }

    idx = pd.bdate_range("2024-01-02", periods=3)

    def _fake_connect(_: object) -> object:
        return object()

    def _fake_disconnect(_: object | None) -> None:
        return None

    def _fake_future(*_args, **kwargs) -> pd.Series:
        base = 18.0 if kwargs.get("position", 0) == 0 else 20.0
        values = [base + i for i in range(len(idx))]
        return pd.Series(values, index=idx)

    def _fake_index(*_args, **_kwargs) -> pd.Series:
        values = [100.0 + i for i in range(len(idx))]
        return pd.Series(values, index=idx)

    monkeypatch.setattr(msb_vendor, "_connect_ibkr", _fake_connect)
    monkeypatch.setattr(msb_vendor, "_disconnect_ibkr", _fake_disconnect)
    monkeypatch.setattr(msb_vendor, "_download_close_series_ibkr_future", _fake_future)
    monkeypatch.setattr(msb_vendor, "_download_close_series_ibkr_index", _fake_index)

    vendor_dir = tmp_path / "vendor"
    status = msb_vendor.refresh_vendor_data(vendor_dir, env=env)

    assert status["vx1"] == "refreshed"
    assert status["vx2"] == "refreshed"
    assert status["spx_ret"] == "refreshed"
    assert (vendor_dir / "vx1.csv").exists()
    assert (vendor_dir / "vx2.csv").exists()
    assert (vendor_dir / "spx_ret.csv").exists()
