"""Command line: print the verdict JSON for an Adapty A/B test."""
import argparse
import json
import sys

from verdict_agent import service


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="python -m verdict_agent.cli", description="Read-only verdict for an Adapty A/B test.")
    parser.add_argument("ab_test_id")
    parser.add_argument("--horizon", type=int)
    parser.add_argument("--replay", metavar="DIR")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = vars(_parser().parse_args(argv))
    except ValueError as exc:
        result = {"error": str(exc)}
    else:
        result = service.safe_verdict(**args)
    print(json.dumps(result, indent=2))
    return 1 if "error" in result else 0


if __name__ == "__main__":
    sys.exit(main())
