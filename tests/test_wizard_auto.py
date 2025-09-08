import json
from typing import List, Dict, Any

import builtins
import types

from portfolio_exporter.scripts import order_builder as ob


def _cand_vert(expiry: str = "2099-01-19") -> List[Dict[str, Any]]:
    return [
        {
            "profile": "balanced",
            "underlying": "TEST",
            "expiry": expiry,
            "legs": [
                {"secType": "OPT", "right": "P", "strike": 100.0, "qty": -1, "expiry": expiry},
                {"secType": "OPT", "right": "P", "strike": 95.0, "qty": 1, "expiry": expiry},
            ],
            "credit": 1.25,
            "width": 5.0,
            "max_loss": 3.75,
            "pop_proxy": 0.8,
        }
    ]


def _cand_ic(expiry: str = "2099-01-19") -> List[Dict[str, Any]]:
    return [
        {
            "profile": "balanced",
            "underlying": "TEST",
            "expiry": expiry,
            "legs": [
                {"secType": "OPT", "right": "P", "strike": 95.0, "qty": -1, "expiry": expiry},
                {"secType": "OPT", "right": "P", "strike": 90.0, "qty": 1, "expiry": expiry},
                {"secType": "OPT", "right": "C", "strike": 105.0, "qty": -1, "expiry": expiry},
                {"secType": "OPT", "right": "C", "strike": 110.0, "qty": 1, "expiry": expiry},
            ],
            "credit": 2.5,
            "width": 5.0,
            "max_loss": 2.5,
        }
    ]


def _cand_fly(expiry: str = "2099-01-19") -> List[Dict[str, Any]]:
    return [
        {
            "profile": "balanced",
            "underlying": "TEST",
            "expiry": expiry,
            "legs": [
                {"secType": "OPT", "right": "C", "strike": 95.0, "qty": 1, "expiry": expiry},
                {"secType": "OPT", "right": "C", "strike": 100.0, "qty": -2, "expiry": expiry},
                {"secType": "OPT", "right": "C", "strike": 105.0, "qty": 1, "expiry": expiry},
            ],
            "debit": 1.25,
            "width": 5.0,
        }
    ]


def test_wizard_auto_vertical_candidates(monkeypatch, capsys):
    # Monkeypatch preset_engine.suggest_credit_vertical to avoid network
    import portfolio_exporter.core.preset_engine as pe

    monkeypatch.setattr(pe, "suggest_credit_vertical", lambda *a, **k: _cand_vert())

    rc = ob.cli([
        "--wizard", "--auto",
        "--strategy", "vertical",
        "--right", "P",
        "--symbol", "TEST",
        "--expiry", "2099-01-19",
        "--json", "--no-files",
    ])
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["ok"] is True and data.get("wizard") is True
    assert isinstance(data.get("candidates"), list) and len(data["candidates"]) >= 1
    assert data.get("resolved_expiry") == "2099-01-19"


def test_wizard_auto_vertical_pick(monkeypatch, capsys):
    import portfolio_exporter.core.preset_engine as pe

    monkeypatch.setattr(pe, "suggest_credit_vertical", lambda *a, **k: _cand_vert())

    rc = ob.cli([
        "--wizard", "--auto",
        "--strategy", "vertical",
        "--right", "P",
        "--symbol", "TEST",
        "--expiry", "2099-01-19",
        "--pick", "1",
        "--json", "--no-files",
    ])
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data.get("picked") == 1
    ticket = data.get("ticket")
    assert ticket and ticket.get("strategy") == "vertical"
    legs = ticket.get("legs", [])
    assert len(legs) == 2 and all(l.get("right") == "P" for l in legs)


def test_wizard_auto_iron_condor_candidates(monkeypatch, capsys):
    import portfolio_exporter.core.preset_engine as pe

    monkeypatch.setattr(pe, "suggest_iron_condor", lambda *a, **k: _cand_ic())

    rc = ob.cli([
        "--wizard", "--auto",
        "--strategy", "iron_condor",
        "--symbol", "TEST",
        "--expiry", "2099-01-19",
        "--json", "--no-files",
    ])
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["ok"] is True and data.get("wizard") is True
    cands = data.get("candidates", [])
    assert cands and len(cands[0].get("legs", [])) == 4


def test_wizard_auto_butterfly_candidates(monkeypatch, capsys):
    import portfolio_exporter.core.preset_engine as pe

    monkeypatch.setattr(pe, "suggest_butterfly", lambda *a, **k: _cand_fly())

    rc = ob.cli([
        "--wizard", "--auto",
        "--strategy", "butterfly",
        "--right", "C",
        "--symbol", "TEST",
        "--expiry", "2099-01-19",
        "--json", "--no-files",
    ])
    out = capsys.readouterr().out.strip()
    data = json.loads(out)
    assert data["ok"] is True and data.get("wizard") is True
    cands = data.get("candidates", [])
    assert cands and len(cands[0].get("legs", [])) == 3
