import json
import subprocess
import sys


def test_cli_vertical_leg_signs(monkeypatch, tmp_path):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))
    cmd = [
        sys.executable,
        "-m",
        "portfolio_exporter.scripts.order_builder",
        "--strategy",
        "vertical",
        "--symbol",
        "XYZ",
        "--right",
        "C",
        "--expiry",
        "2025-01-17",
        "--strikes",
        "100,110",
        "--qty",
        "1",
    ]
    subprocess.check_call(cmd)
    ticket_path = next(tmp_path.glob("ticket_*.json"))
    data = json.loads(ticket_path.read_text())
    legs = [(leg["right"], leg["strike"], leg["qty"]) for leg in data["legs"]]
    assert legs == [("C", 100, 1), ("C", 110, -1)]
