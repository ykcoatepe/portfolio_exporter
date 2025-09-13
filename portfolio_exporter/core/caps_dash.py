from rich.live import Live
from rich.table import Table
from time import sleep
import datetime as _dt

from portfolio_exporter.scripts import theta_cap, gamma_scalp

REFRESH = 5  # seconds


def _render():
    θ_data = theta_cap.run(return_dict=True)
    γ_data = gamma_scalp.run(return_dict=True)

    tbl = Table(title=f"Theta / Gamma Caps – {_dt.datetime.now():%H:%M:%S}")
    tbl.add_column("Metric")
    tbl.add_column("Value", justify="right")

    tbl.add_row("3-day θ-% vs floor", f"{θ_data['theta_pct']:+.1%}")
    tbl.add_row("Net Δ short", f"{θ_data['net_delta']:+.2f}")
    tbl.add_row("Γ-scalp used %", f"{γ_data['used_bucket']:.1%}")
    return tbl


def run():
    with Live(_render(), refresh_per_second=4) as live:
        try:
            while True:
                sleep(REFRESH)
                live.update(_render())
        except KeyboardInterrupt:
            pass
