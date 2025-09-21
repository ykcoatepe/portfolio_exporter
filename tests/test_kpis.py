from __future__ import annotations

from src.psd.analytics.kpis import per_sleeve_kpis


def test_kpis_per_sleeve():
    memos = [
        {"sleeve": "momo", "R": 1.2, "win": True, "theta_roc": 0.01, "cost": 2.0, "nav": 1000},
        {"sleeve": "momo", "R": 0.0, "win": False, "theta_roc": 0.00, "cost": 1.0, "nav": 1000},
        {"sleeve": "alpha", "R": 1.0, "win": True, "theta_roc": 0.00, "cost": 1.0, "nav": 1000},
        {"sleeve": "alpha", "R": 0.2, "win": True, "theta_roc": 0.00, "cost": 1.0, "nav": 1000},
    ]
    k = per_sleeve_kpis(memos)
    assert k["momo"]["win_rate"] >= 0.5
    assert k["alpha"]["avg_R"] >= 0.6
    assert k["momo"]["theta_ROC"] >= 0.005

