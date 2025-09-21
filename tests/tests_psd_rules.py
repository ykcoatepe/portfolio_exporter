from __future__ import annotations

import os

import pytest

from portfolio_exporter import psd_rules


def test_rules_triggers_and_defaults(monkeypatch):
    risk = {"beta": 0.05, "var95_1d": 5_000.0, "notional": 100_000.0, "margin_pct": 0.4}
    monkeypatch.delenv("PSD_RULE_BETA_MIN", raising=False)
    monkeypatch.delenv("PSD_RULE_VAR95_1D_MAX", raising=False)
    monkeypatch.delenv("PSD_RULE_MARGIN_MAX", raising=False)

    breaches = psd_rules.evaluate(risk)
    assert set(breaches) == {"beta_low", "var_spike", "margin_high"}


def test_rules_missing_keys(monkeypatch):
    monkeypatch.delenv("PSD_RULE_BETA_MIN", raising=False)
    assert psd_rules.evaluate({}) == ["beta_low"]
    assert psd_rules.evaluate(None) == ["beta_low"]


def test_rules_env_override(monkeypatch):
    monkeypatch.setenv("PSD_RULE_BETA_MIN", "0.01")
    monkeypatch.setenv("PSD_RULE_VAR95_1D_MAX", "0.50")
    monkeypatch.setenv("PSD_RULE_MARGIN_MAX", "0.90")
    risk = {"beta": 0.02, "VaR95_1d": 2_000.0, "notional": 100_000.0, "margin_used": 0.5}

    breaches = psd_rules.evaluate(risk)
    assert breaches == []
