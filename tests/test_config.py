from portfolio_exporter.core.config import settings


def test_timezone():
    assert settings.timezone == "Europe/Istanbul"
