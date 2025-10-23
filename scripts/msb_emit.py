"""CLI helper to broadcast the latest MSB reading via SSE."""

from __future__ import annotations

import argparse
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Broadcast the latest MSB reading to connected SSE subscribers."
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="suppress human-readable output; exit code still indicates success",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:51127/msb/broadcast",
        help="HTTP endpoint on the running PSD server to request MSB broadcast "
        "(default: %(default)s)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP request timeout in seconds (default: %(default)s)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    request = Request(args.url, method="POST")

    try:
        with urlopen(request, timeout=args.timeout) as response:
            status = response.getcode()
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        if not args.quiet:
            print(f"broadcast request failed: {exc.code} {exc.reason}", file=sys.stderr)
        raise SystemExit(1)
    except URLError as exc:
        if not args.quiet:
            print(f"broadcast request failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:  # pragma: no cover - defensive
        if not args.quiet:
            print(f"unexpected error: {exc}", file=sys.stderr)
        raise SystemExit(1)

    if status == 200:
        if not args.quiet:
            print(body or "msb.update broadcast dispatched")
        raise SystemExit(0)

    if not args.quiet:
        print(f"unexpected response ({status}): {body}", file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
