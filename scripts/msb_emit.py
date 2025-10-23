"""CLI helper to broadcast the latest MSB reading via SSE."""

from __future__ import annotations

import argparse
import sys

from psd.web.app import broadcast_latest_msb, create_app
from psd.web.config import Settings, get_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Broadcast the latest MSB reading to connected SSE subscribers."
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress human-readable output; exit code still indicates success",
    )
    return parser


def _resolve_settings() -> Settings:
    base = get_settings()
    return base.model_copy(update={"disable_background": True})


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    app = create_app(_resolve_settings())
    success = broadcast_latest_msb(app)

    if args.quiet:
        raise SystemExit(0 if success else 1)

    if success:
        print("msb.update broadcast dispatched")
        raise SystemExit(0)

    print("no MSB reading available", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()

