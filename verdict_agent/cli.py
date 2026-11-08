"""Command line: print the verdict JSON for an Adapty A/B test."""
import argparse
import json
import sys
from datetime import date

from verdict_agent import service
from verdict_agent.card import render_card
from verdict_agent.model import VerdictError


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise VerdictError(message)


def _as_of(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"--as-of must be YYYY-MM-DD, got {value!r}") from None


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m verdict_agent.cli", description="Read-only verdict for an Adapty A/B test.")
    parser.add_argument("ab_test_id")
    parser.add_argument("--horizon", type=int)
    parser.add_argument("--after-days", dest="after_days", type=int, metavar="N",
                        help="days the shipped arm serves the test's traffic after the stop (default 180)")
    parser.add_argument("--replay", metavar="DIR")
    parser.add_argument("--app", dest="app_id", metavar="APP_ID", help="Adapty app id; wins over ADAPTY_APP_ID")
    parser.add_argument("--as-of", dest="as_of", type=_as_of, metavar="YYYY-MM-DD",
                        help="day to judge the test on; on replay defaults to the bundle's as_of.json")
    parser.add_argument("--format", dest="output_format", choices=("json", "card"), default="json",
                        help="json (default) or card: a short text summary for a person")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = vars(_parser().parse_args(argv))
    except VerdictError as exc:
        raw = argv if argv is not None else sys.argv[1:]
        card = "card" in raw[raw.index("--format") + 1:raw.index("--format") + 2] if "--format" in raw else False
        args, result = {"output_format": "card" if card or "--format=card" in raw else "json"}, {"error": str(exc)}
    else:
        output_format = args.pop("output_format")
        result = service.safe_verdict(**args)
        args["output_format"] = output_format
    if args.get("output_format") == "card":
        print(render_card(result))
    else:
        print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
