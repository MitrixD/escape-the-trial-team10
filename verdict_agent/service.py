"""One entry point for the CLI and the MCP tool: the verdict for an Adapty A/B test, with safe errors."""
import sys
from datetime import date
from pathlib import Path

from verdict_agent.adapty_cli import CliError, RateLimited, ReadOnlyViolation, WrongAccount
from verdict_agent.live import run_live
from verdict_agent.model import VerdictError

KNOWN_ERRORS = (VerdictError, WrongAccount, RateLimited, ReadOnlyViolation)


def verdict(ab_test_id: str, horizon: int | None = None, replay: str | None = None,
            app_id: str | None = None, as_of: date | None = None, after_days: int | None = None) -> dict:
    return run_live(ab_test_id, horizon=horizon, replay=Path(replay) if replay else None, app_id=app_id, today=as_of,
                    after_days=after_days)


def _log_detail(exc: Exception) -> None:
    detail = " ".join(str(exc).split())
    print(f"verdict-agent: {type(exc).__name__}: {detail}", file=sys.stderr)


def safe_verdict(**kwargs) -> dict:
    try:
        return verdict(**kwargs)
    except KNOWN_ERRORS as exc:
        return {"error": str(exc)}
    except CliError as exc:
        _log_detail(exc)
        return {"error": exc.public}
    except Exception as exc:
        _log_detail(exc)
        return {"error": f"unexpected {type(exc).__name__}"}
