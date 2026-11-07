import json
import subprocess
from pathlib import Path

import pytest

from verdict_agent.adapty_cli import AdaptyCLI, CliError, RateLimited, ReadOnlyViolation, WrongAccount, replay_runner

COMPANY = "Synthetic Co"
LIVE = Path(__file__).parent / "fixtures" / "live"
BUNDLES = sorted(p for p in LIVE.iterdir() if p.is_dir())


class FakeRunner:
    def __init__(self):
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        body = {"company": COMPANY, "email": "dev@example.test"} if cmd[1:3] == ["auth", "whoami"] else {"ok": True}
        return subprocess.CompletedProcess(cmd, 0, json.dumps(body), "")


class Clock:
    def __init__(self):
        self.now = 100.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, s):
        self.sleeps.append(s)
        self.now += s


def make(runner=None):
    clock = Clock()
    return AdaptyCLI(runner=runner or FakeRunner(), clock=clock, sleep=clock.sleep), clock


@pytest.mark.parametrize("args", [
    ["ab-tests", "stop", "x"], ["ab-tests", "start", "x"], ["ab-tests", "create"], ["ab-tests", "archive", "x"],
    ["flows", "publish", "x"], ["products", "update", "x"], ["auth", "login"],
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


@pytest.mark.parametrize("value", ["soon", None, [], "1.5"])
def test_non_numeric_retry_after_is_unknown(value):
    def runner(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 4, json.dumps({"retry_after_seconds": value}), "")

    cli, _ = make(runner)
    with pytest.raises(RateLimited) as err:
        cli.run(["ab-tests", "get", "x"])
    assert err.value.retry_after is None


def test_bundles_have_no_cohort_recording_and_replay_refuses_it():
    for bundle in BUNDLES:
        assert not (bundle / "analytics_cohort.json").exists()
    with pytest.raises(CliError, match="no recorded file"):
        replay_cli(BUNDLES[0]).run(["analytics", "cohort", "--app", "a"])


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


def test_cli_error():
    cli, _ = make(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, "", "x" * 500))
    with pytest.raises(CliError) as err:
        cli.run(["ab-tests", "get", "x"])
    assert err.value.exit_code == 2
    assert err.value.stderr == "x" * 300
    assert err.value.public == "adapty exited with code 2"


def test_cli_error_public_message_has_context_without_stderr():
    err = CliError(1, "secret detail", context="cannot read A/B test abc")
    assert err.public == "cannot read A/B test abc: adapty exited with code 1"
    assert "secret detail" in str(err) and "secret detail" not in err.public


def test_non_json_output_is_cli_error():
    cli, _ = make(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "not json", ""))
    with pytest.raises(CliError):
        cli.run(["ab-tests", "get", "x"])


def test_check_account_passes_on_any_string_value():
    cli, _ = make()
    cli.check_account(COMPANY)


@pytest.mark.parametrize("expected", ["Other Company", "", "Synthetic"])
def test_wrong_account(expected):
    cli, _ = make()
    with pytest.raises(WrongAccount) as err:
        cli.check_account(expected)
    assert COMPANY not in str(err.value)
    assert "dev@example.test" not in str(err.value)
    if expected:
        assert expected not in str(err.value)
        assert "ADAPTY_EXPECTED_COMPANY" in str(err.value)


def test_whoami_error_hides_stderr():
    cli, _ = make(lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "logged in as someone@example.test"))
    with pytest.raises(CliError) as err:
        cli.check_account(COMPANY)
    assert "someone@example.test" not in str(err.value)


def no_subprocess(*a, **kw):
    raise AssertionError("subprocess must not be used on replay")


def replay_cli(bundle):
    return AdaptyCLI(runner=replay_runner(bundle), sleep=lambda s: None)


def test_replay_bundles_exist():
    assert len(BUNDLES) >= 2


@pytest.mark.parametrize("bundle", BUNDLES, ids=lambda p: p.name[:8])
def test_replay_serves_every_recorded_file(bundle):
    cli = replay_cli(bundle)
    assert cli.run(["auth", "whoami"]) == json.loads((bundle / "auth_whoami.json").read_text())
    assert cli.run(["ab-tests", "get", "any"]) == json.loads((bundle / "ab-tests_get.json").read_text())
    assert cli.run(["ab-tests", "metrics", "total", "any"]) == json.loads((bundle / "ab-tests_metrics_total.json").read_text())
    assert cli.run(["products", "list", "--app-id", "a"]) == json.loads((bundle / "products_list.json").read_text())
    assert cli.run(["analytics", "ltv", "--app-id", "a"]) == json.loads((bundle / "analytics_ltv.json").read_text())
    conv = ["analytics", "conversion", "--conversion", "trial-paid"]
    assert cli.run(conv) == json.loads((bundle / "analytics_conversion_trial-paid.json").read_text())
    for f in bundle.glob("analytics_funnel_*.json"):
        flow_id = f.stem.removeprefix("analytics_funnel_")
        for filt in (["--filter", f"flow_id={flow_id}"], [f"--filter=flow_id={flow_id}"]):
            assert cli.run(["analytics", "funnel", *filt]) == json.loads(f.read_text())


def test_replay_never_uses_subprocess(monkeypatch):
    monkeypatch.setattr(subprocess, "run", no_subprocess)
    cli = replay_cli(BUNDLES[0])
    cli.run(["ab-tests", "get", "x"])


def test_replay_missing_file_names_command_and_file(tmp_path):
    cli = replay_cli(tmp_path)
    with pytest.raises(CliError) as err:
        cli.run(["products", "list"])
    assert "products list" in str(err.value) and "products_list.json" in str(err.value)
    assert "products_list.json" in err.value.public


def test_replay_unknown_command_is_cli_error(tmp_path):
    cli = replay_cli(tmp_path)
    with pytest.raises(CliError) as err:
        cli.run(["analytics", "retention"])
    assert "analytics retention" in str(err.value)


def test_replay_funnel_without_flow_filter_is_cli_error():
    cli = replay_cli(BUNDLES[0])
    with pytest.raises(CliError) as err:
        cli.run(["analytics", "funnel"])
    assert "flow_id" in str(err.value)


def test_replay_check_account_follows_matched_flag(tmp_path):
    for flag, ok in ((True, True), (False, False)):
        (tmp_path / "auth_whoami.json").write_text(json.dumps({"company": "<redacted>", "matched_expected_company": flag}))
        cli = replay_cli(tmp_path)
        if ok:
            cli.check_account("anything")
        else:
            with pytest.raises(WrongAccount):
                cli.check_account("anything")


@pytest.mark.parametrize("bundle", BUNDLES, ids=lambda p: p.name[:8])
def test_replay_check_account_passes_on_recorded_bundle(bundle):
    replay_cli(bundle).check_account("whatever")
