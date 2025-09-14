from portfolio_exporter.core.providers.halts_nasdaq import parse_resume_events


def test_parse_resume_events_basic():
    rows = [
        {
            "Issue Symbol": "ABC",
            "Halt Time": "14:30:00",
            "Resumption Quote Time": "14:35:00",
            "Resumption Trade Time": "14:35:30",
            "Reason Code": "LUDP",
        },
        {
            "Issue Symbol": "NORES",
            "Halt Time": "10:00:00",
            "Resumption Quote Time": "",
            "Resumption Trade Time": "",
            "Reason Code": "T1",
        },
    ]
    ev = parse_resume_events(rows)
    assert "ABC" in ev
    assert ev["ABC"]["resume_quote_et"] == "14:35:00"
    assert ev["ABC"]["resume_trade_et"] == "14:35:30"
    assert ev["ABC"]["reason"] == "LUDP"
    assert "NORES" not in ev

