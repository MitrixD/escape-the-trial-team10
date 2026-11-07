"""Command line: print the verdict JSON for a live A/B test or an offline test."""
import argparse
import json
import sys

from verdict_agent import service
from verdict_agent.adapty_cli import CliError, RateLimited, ReadOnlyViolation, WrongAccount

KNOWN_ERRORS = (ValueError, WrongAccount, RateLimited, CliError, ReadOnlyViolation)


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m verdict_agent.cli", description="Read-only verdict for an Adapty A/B test.")
    sub = parser.add_subparsers(dest="mode", required=True)
    live = sub.add_parser("live", help="verdict for a live Adapty A/B test")
    live.add_argument("ab_test_id")
    live.add_argument("--horizon", type=int)
    offline = sub.add_parser("offline", help="verdict for a test in the offline Lumen dataset")
    offline.add_argument("offline_test")
    offline.add_argument("--day", type=int, default=14)
    offline.add_argument("--traffic", type=int, default=100)
    offline.add_argument("--horizon", type=int)
    return parser


def safe_verdict(**kwargs) -> dict:
    try:
        return service.verdict(**kwargs)
    except KNOWN_ERRORS as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"unexpected {type(exc).__name__}: {exc}"}


def main(argv: list[str] | None = None) -> int:
    try:
        args = vars(_parser().parse_args(argv))
    except ValueError as exc:
        result = {"error": str(exc)}
    else:
        args.pop("mode")
        result = safe_verdict(**args)
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
