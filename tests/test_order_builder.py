import builtins, types, pathlib, json
from portfolio_exporter.scripts import order_builder
from portfolio_exporter.core.config import settings


def test_order_builder_creates_file(monkeypatch, tmp_path):
    # Redirect output_dir to temp
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))
    answers = iter(["AAPL 150c 2099-01-01 x2", "", "", "", "", ""])
    monkeypatch.setattr(builtins, "input", lambda _="": next(answers))
    monkeypatch.setattr(builtins, "prompt_toolkit.prompt", lambda x, **k: next(answers))
    order_builder.run()
    tickets = list((tmp_path / "tickets").glob("ticket_*.json"))
    assert tickets, "No ticket file created"
    data = json.loads(tickets[0].read_text())
    assert data["underlying"] == "AAPL"
    assert data["qty"] == 2
