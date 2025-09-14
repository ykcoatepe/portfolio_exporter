from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import List


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser("micro-momo-go")
    ap.add_argument("--symbols", help="comma list (optional)")
    ap.add_argument("--cfg", default="micro_momo_config.json")
    ap.add_argument("--out_dir", default="out")
    ap.add_argument("--providers", default=os.getenv("MOMO_PROVIDERS", "ib,yahoo"))
    ap.add_argument("--data-mode", default=os.getenv("MOMO_DATA_MODE", "enrich"))
    ap.add_argument("--webhook", help="alerts webhook (optional)")
    ap.add_argument("--ib-basket-out", default="out/micro_momo_basket.csv")
    ap.add_argument("--start-sentinel", action="store_true")
    ap.add_argument("--thread", help="Slack thread_ts (optional)")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--auto-producers", action="store_true")
    args = ap.parse_args(argv)

    from portfolio_exporter.scripts import micro_momo_analyzer as ana
    from portfolio_exporter.scripts import micro_momo_dashboard as dash

    Path(args.out_dir).mkdir(parents=True, exist_ok=True)

    # 1) Analyze (+journal + basket + optional webhook to let you know run started)
    argv_ana: List[str] = [
        "--out_dir",
        args.out_dir,
        "--data-mode",
        args.data_mode,
        "--providers",
        args.providers,
        "--journal-template",
        "--ib-basket-out",
        args.ib_basket_out,
    ]
    if args.cfg and Path(args.cfg).exists():
        argv_ana += ["--cfg", args.cfg]
    if args.symbols:
        argv_ana += ["--symbols", args.symbols]
    if args.webhook:
        argv_ana += ["--webhook", args.webhook]
    if args.offline:
        argv_ana += ["--offline"]
    if args.auto_producers:
        argv_ana += ["--auto-producers"]
    ana.main(argv_ana)

    # 2) Dashboard (always)
    dash.main(["--out_dir", args.out_dir])

    # 3) Optional sentinel (non-blocking hint: user typically runs in separate terminal)
    if args.start_sentinel:
        from portfolio_exporter.scripts import micro_momo_sentinel as sen

        argv_sen: List[str] = [
            "--scored-csv",
            os.path.join(args.out_dir, "micro_momo_scored.csv"),
            "--cfg",
            args.cfg,
            "--out_dir",
            args.out_dir,
            "--interval",
            "10",
        ]
        if args.webhook:
            argv_sen += ["--webhook", args.webhook]
        if args.thread:
            argv_sen += ["--thread", args.thread]
        if args.offline:
            argv_sen += ["--offline"]
        # Run inline (user can ^C or open a second terminal)
        sen.main(argv_sen)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

