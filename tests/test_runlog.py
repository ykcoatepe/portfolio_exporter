import pytest
from portfolio_exporter.core.runlog import RunLog


def test_runlog_timings(monkeypatch):
    import portfolio_exporter.core.runlog as rl_mod

    calls = [0.0, 0.1, 0.2, 0.3, 0.4]  # enter + two stages
    def fake_perf_counter():
        return calls.pop(0)

    monkeypatch.setattr(rl_mod, 'perf_counter', fake_perf_counter)

    with RunLog(script='test') as rl:
        with rl.time('stage1'):
            pass
        with rl.time('stage2'):
            pass
    assert rl.timings == [
        {'stage': 'stage1', 'ms': 100},
        {'stage': 'stage2', 'ms': 100},
    ]
