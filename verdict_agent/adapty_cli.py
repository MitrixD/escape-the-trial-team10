"""Read-only wrapper around the Adapty CLI: allowlisted commands, spaced calls, stop on rate limit."""
import json
import subprocess
import time

READ_VERBS = {"get", "list"}
STDERR_LIMIT = 300


class ReadOnlyViolation(Exception):
    pass


class WrongAccount(Exception):
    pass


class CliError(Exception):
    def __init__(self, exit_code: int, stderr: str):
        self.exit_code = exit_code
        self.stderr = stderr[:STDERR_LIMIT]
        super().__init__(f"adapty exited with code {exit_code}: {self.stderr}")


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Adapty rate limit hit, retry after {retry_after} seconds")


def is_read_command(args: list[str]) -> bool:
    if len(args) < 2 or args[0] == "profiles":
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
        if value is not None:
            return int(value)
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
            retry = _retry_after(proc.stdout or "", proc.stderr or "")
            if retry is not None:
                self._rate_limited = RateLimited(retry)
                raise self._rate_limited
        if proc.returncode != 0:
            raise CliError(proc.returncode, proc.stderr or "")
        return json.loads(proc.stdout)

    def check_account(self, expected_company: str) -> None:
        if not expected_company:
            raise WrongAccount("expected Adapty company is not set (ADAPTY_EXPECTED_COMPANY)")
        whoami = self.run(["auth", "whoami"])
        if expected_company not in set(_strings(whoami)):
            raise WrongAccount(f"Adapty CLI is not logged in to the expected company {expected_company!r}")
