"""Read-only wrapper around the Adapty CLI: allowlisted commands, spaced calls, stop on rate limit."""
import json
import subprocess
import time
from pathlib import Path

READ_VERBS = {"get", "list"}
DENIED = {("apps", "get")}
STDERR_LIMIT = 300


class ReadOnlyViolation(Exception):
    pass


class WrongAccount(Exception):
    pass


class CliError(Exception):
    def __init__(self, exit_code: int, stderr: str, context: str | None = None):
        self.exit_code = exit_code
        self.stderr = stderr[:STDERR_LIMIT]
        self.context = context
        base = f"adapty exited with code {exit_code}"
        self.public = f"{context}: {base}" if context else base
        super().__init__(f"{self.public}: {self.stderr}")


class RateLimited(Exception):
    def __init__(self, retry_after: int | None):
        self.retry_after = retry_after
        wait = f"retry after {retry_after} seconds" if retry_after is not None else "retry time unknown"
        super().__init__(f"Adapty rate limit hit, {wait}; stopping without further calls")


def is_read_command(args: list[str]) -> bool:
    if len(args) < 2 or args[0] == "profiles" or tuple(args[:2]) in DENIED:
        return False
    topic, verb = args[0], args[1]
    return (
        (topic, verb) == ("auth", "whoami")
        or verb in READ_VERBS
        or (topic, verb) == ("ab-tests", "metrics")
        or topic == "analytics"
    )


def _retry_after(*streams: str) -> int | None:
    for text in streams:
        try:
            value = json.loads(text).get("retry_after_seconds")
        except (ValueError, AttributeError):
            continue
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


class AdaptyCLI:
    def __init__(self, runner=subprocess.run, clock=time.monotonic, sleep=time.sleep, min_interval=0.5):
        self.runner = runner
        self.clock = clock
        self.sleep = sleep
        self.min_interval = min_interval
        self._last: float | None = None
        self._rate_limited: RateLimited | None = None

    def run(self, args: list[str]) -> dict:
        if not is_read_command(args):
            raise ReadOnlyViolation(f"not a read-only Adapty command: {' '.join(args[:2])}")
        if self._rate_limited:
            raise self._rate_limited
        if self._last is not None:
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
        try:
            proc = self.runner(["adapty", *args, "--json"], capture_output=True, text=True)
        finally:
            self._last = self.clock()
        if proc.returncode == 4:
            self._rate_limited = RateLimited(_retry_after(proc.stdout or "", proc.stderr or ""))
            raise self._rate_limited
        private = args[:2] == ["auth", "whoami"]
        if proc.returncode != 0:
            raise CliError(proc.returncode, "<hidden for auth whoami>" if private else proc.stderr or "")
        try:
            return json.loads(proc.stdout)
        except (TypeError, ValueError):
            raise CliError(proc.returncode, f"{' '.join(args[:2])} did not return JSON") from None

    def check_account(self, expected_company: str) -> None:
        if not expected_company:
            raise WrongAccount("expected Adapty company is not set (ADAPTY_EXPECTED_COMPANY)")
        whoami = self.run(["auth", "whoami"])
        if "matched_expected_company" in whoami:
            matched = whoami["matched_expected_company"] is True
        else:
            matched = expected_company in set(_strings(whoami))
        if not matched:
            raise WrongAccount(
                "Adapty CLI is not logged in to the expected company; "
                "run `adapty auth whoami` and check ADAPTY_EXPECTED_COMPANY (environment or .env)"
            )


def _replay_file(args: list[str]) -> str | None:
    key = tuple(args[:2])
    if key == ("auth", "whoami"):
        return "auth_whoami.json"
    if key == ("ab-tests", "get"):
        return "ab-tests_get.json"
    if args[:3] == ["ab-tests", "metrics", "total"]:
        return "ab-tests_metrics_total.json"
    if key == ("products", "list"):
        return "products_list.json"
    if key == ("analytics", "ltv"):
        return "analytics_ltv.json"
    if key == ("analytics", "conversion"):
        conversion = _option(args, "--conversion")
        return f"analytics_conversion_{conversion}.json" if conversion else None
    if key == ("analytics", "funnel"):
        flow_id = _option(args, "--filter", prefix="flow_id=")
        return f"analytics_funnel_{flow_id}.json" if flow_id else None
    return None


def _option(args: list[str], name: str, prefix: str = "") -> str | None:
    for i, arg in enumerate(args):
        if arg == name and i + 1 < len(args):
            value = args[i + 1]
        elif arg.startswith(name + "="):
            value = arg[len(name) + 1:]
        else:
            continue
        if value.startswith(prefix):
            return value[len(prefix):]
    return None


def replay_runner(directory: Path):
    directory = Path(directory)

    def runner(cmd, **kwargs):
        args = [a for a in cmd[1:] if a != "--json"]
        name = _replay_file(args)
        shown = " ".join(args)
        if name is None:
            raise CliError(1, "", context=f"replay cannot serve `adapty {shown}`: no recorded file for this command (funnel needs --filter flow_id=<id>, conversion needs --conversion <name>)")
        path = directory / name
        if not path.is_file():
            raise CliError(1, "", context=f"replay has no recording for `adapty {shown}`: expected {name}")
        return subprocess.CompletedProcess(cmd, 0, path.read_text(), "")

    return runner
