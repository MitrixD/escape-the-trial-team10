import json
import subprocess

import pytest

from tests.live_fakes import COMPANY, FakeRunner
from verdict_agent.adapty_cli import AdaptyCLI, CliError, RateLimited, ReadOnlyViolation, WrongAccount


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps: list[float] = []

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def make(runner=None, clock=None):
    clock = clock or Clock()
    return AdaptyCLI(runner=runner or FakeRunner(), clock=clock, sleep=clock.sleep), clock


@pytest.mark.parametrize("args", [
    ["ab-tests", "stop", "x"], ["ab-tests", "start", "x"], ["ab-tests", "create"], ["ab-tests", "archive", "x"],
    ["ab-tests", "replace", "x"], ["flows", "publish", "x"], ["products", "update", "x"], ["auth", "login"],
    ["profiles", "list"], ["profiles", "get", "x"], ["apps", "get", "x"], [], ["ab-tests"],
])
def test_rejects_mutating_command(args):
    runner = FakeRunner()
    cli, _ = make(runner)
    with pytest.raises(ReadOnlyViolation):
        cli.run(args)
    assert runner.calls == []


@pytest.mark.parametrize("args", [
    ["auth", "whoami"], ["ab-tests", "get", "x"], ["apps", "list"], ["ab-tests", "metrics", "total", "x"],
    ["analytics", "funnel"],
])
def test_allows_read_commands_and_appends_json(args):
    runner = FakeRunner()
    cli, _ = make(runner)
    cli.run(args)
    assert runner.calls == [["adapty", *args, "--json"]]


def test_spacing():
    cli, clock = make()
    cli.run(["auth", "whoami"])
    clock.now += 0.2
    cli.run(["auth", "whoami"])
    assert clock.sleeps == [pytest.approx(0.3)]
    clock.now += 5
    cli.run(["auth", "whoami"])
    assert clock.sleeps == [pytest.approx(0.3)]


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_rate_limited(stream):
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        body = json.dumps({"error": "too many requests", "retry_after_seconds": 12})
        return subprocess.CompletedProcess(cmd, 4, body if stream == "stdout" else "", body if stream == "stderr" else "")

    cli, _ = make(runner)
    with pytest.raises(RateLimited) as err:
        cli.run(["ab-tests", "get", "x"])
    assert err.value.retry_after == 12
    assert "12" in str(err.value)
    with pytest.raises(RateLimited):
        cli.run(["ab-tests", "get", "y"])
    assert len(calls) == 1


def test_cli_error():
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 2, "", "x" * 500)

    cli, _ = make(runner)
    with pytest.raises(CliError) as err:
        cli.run(["ab-tests", "get", "x"])
    assert err.value.exit_code == 2
    assert err.value.stderr == "x" * 300
    assert err.value.public == "adapty exited with code 2"


def test_cli_error_public_message_has_context_without_stderr():
    err = CliError(1, "secret detail", context="cannot read A/B test abc")
    assert err.public == "cannot read A/B test abc: adapty exited with code 1"
    assert "secret detail" in str(err) and "secret detail" not in err.public


def test_check_account_passes_on_any_string_value():
    cli, _ = make()
    cli.check_account(COMPANY)


@pytest.mark.parametrize("expected", ["Other Company", "", "Synthetic"])
def test_wrong_account(expected):
    runner = FakeRunner()
    cli, _ = make(runner)
    with pytest.raises(WrongAccount) as err:
        cli.check_account(expected)
    assert COMPANY not in str(err.value)
    assert "dev@example.test" not in str(err.value)
    if expected:
        assert expected not in str(err.value)
        assert "adapty auth whoami" in str(err.value) and "ADAPTY_EXPECTED_COMPANY" in str(err.value)


def test_exit_4_without_retry_after_still_stops():
    calls = []

    def runner(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 4, "rate limited", "")

    cli, _ = make(runner)
    with pytest.raises(RateLimited) as err:
        cli.run(["analytics", "funnel"])
    assert err.value.retry_after is None
    with pytest.raises(RateLimited):
        cli.run(["analytics", "funnel"])
    assert len(calls) == 1


def test_non_json_output_is_cli_error():
    cli, _ = make(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "not json", ""))
    with pytest.raises(CliError):
        cli.run(["ab-tests", "get", "x"])


def test_whoami_error_hides_stderr():
    cli, _ = make(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "logged in as someone@example.test"))
    with pytest.raises(CliError) as err:
        cli.check_account(COMPANY)
    assert "someone@example.test" not in str(err.value) and "someone" not in err.value.stderr
