from __future__ import annotations

import argparse
import os
try:
    # Python 3.9+ exposes BooleanOptionalAction for --flag/--no-flag pairs
    from argparse import BooleanOptionalAction  # noqa: F401

    _HAS_BOA = True
except Exception:  # pragma: no cover - fallback for <3.9
    _HAS_BOA = False

from pathlib import Path
from typing import List


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser("micro-momo-go")
    ap.add_argument("--symbols", help="comma list (optional)")
    ap.add_argument("--cfg", default="micro_momo_config.json")
    ap.add_argument("--out_dir", default="out")
    if _HAS_BOA:
        ap.add_argument(
            "--publish",
            action=BooleanOptionalAction,
            default=True,
            help="Publish outputs (use --no-publish to disable).",
        )
    else:
        ap.add_argument(
            "--publish",
            dest="publish",
            action="store_true",
            default=True,
            help="Publish outputs",
        )
        ap.add_argument(
            "--no-publish",
            dest="publish",
            action="store_false",
            help="Disable publishing",
        )
    ap.add_argument("--publish-dir", default="out/publish")
    ap.add_argument("--providers", default=os.getenv("MOMO_PROVIDERS", "ib,yahoo"))
    ap.add_argument("--data-mode", default=os.getenv("MOMO_DATA_MODE", "enrich"))
    ap.add_argument("--webhook", help="alerts webhook (optional)")
    ap.add_argument("--post-digest", action="store_true")
    ap.add_argument("--ib-basket-out", default="out/micro_momo_basket.csv")
    ap.add_argument("--start-sentinel", action="store_true")
    ap.add_argument("--thread", help="Slack thread_ts (optional)")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--auto-producers", action="store_true")
    ap.add_argument("--session", choices=["auto", "rth", "premarket"], default=os.getenv("MOMO_SESSION"))
    args = ap.parse_args(argv)

    from portfolio_exporter.scripts import micro_momo_analyzer as ana
    from portfolio_exporter.scripts import micro_momo_dashboard as dash
    from ..core.publish import publish_pack, open_dashboard
    from ..core.slack_digest import build_blocks
    from ..core.alerts import emit_alerts
    from ..core.memory import get_pref, set_pref

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
    if args.session:
        argv_ana += ["--session", args.session]
    rc = ana.main(argv_ana)
    if rc != 0:
        return rc

    # 2) Dashboard (always)
    dash.main(["--out_dir", args.out_dir])

    # 3) Publish curated pack (repo-local) and open dashboard
    if args.publish:
        published = publish_pack(args.out_dir, args.publish_dir)
        open_dashboard(published)
        # Optional Slack digest via incoming webhook or Web API
        if args.post_digest:
            import csv

            scored_path = os.path.join(args.out_dir, "micro_momo_scored.csv")
            if os.path.exists(scored_path):
                with open(scored_path, encoding="utf-8") as f:
                    rows = list(csv.DictReader(f))
                payload = build_blocks(rows, published)
                token = os.getenv("MOMO_SLACK_TOKEN")
                channel = os.getenv("MOMO_SLACK_CHANNEL")
                if token and channel:
                    try:
                        from ..core.slack_webapi import post_message

                        api_payload = {"channel": channel, **payload}
                        res = post_message(token, channel, api_payload)
                        if res.get("ok") and res.get("ts"):
                            set_pref("slack.digest_ts", res["ts"])  # persist for sentinel threading
                    except Exception:
                        pass
                elif args.webhook:
                    # Webhook path: one message using Block Kit (no ts returned)
                    emit_alerts(
                        [payload], args.webhook, dry_run=False, offline=bool(args.offline), per_item=True
                    )

    # 4) Optional sentinel (non-blocking hint: user typically runs in separate terminal)
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
        # prefer provided --thread; else use saved digest ts if present
        if args.thread:
            argv_sen += ["--thread", args.thread]
        else:
            try:
                ts = get_pref("slack.digest_ts")
                if ts:
                    argv_sen += ["--thread", ts]
            except Exception:
                pass
        if args.offline:
            argv_sen += ["--offline"]
        # Run inline (user can ^C or open a second terminal)
        sen.main(argv_sen)

    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
