import os
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "record_fixtures.sh"


@pytest.fixture
def fake_adapty(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    tool = bin_dir / "adapty"
    tool.write_text(f'#!/bin/sh\necho "$@" >> "{log}"\necho \'{{"company": "Other Co"}}\'\n')
    tool.chmod(0o755)
    return bin_dir, log


def record(tmp_path, bin_dir, env_text):
    env_file = tmp_path / "test.env"
    env_file.write_text(env_text)
    test_id = f"pytest-{uuid.uuid4()}"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "ENV_FILE": str(env_file)}
    done = subprocess.run([str(SCRIPT), test_id], env=env, capture_output=True, text=True)
    out = REPO / "tests" / "fixtures" / "live" / test_id
    created = out.exists()
    shutil.rmtree(out, ignore_errors=True)
    return done, created


def test_empty_expected_company_is_refused_before_any_call(tmp_path, fake_adapty):
    bin_dir, log = fake_adapty
    done, out = record(tmp_path, bin_dir, "ADAPTY_APP_ID=app-1\nADAPTY_EXPECTED_COMPANY=\n")
    assert done.returncode == 2
    assert "ADAPTY_EXPECTED_COMPANY" in done.stderr
    assert not log.exists() and not out


def test_wrong_company_stops_with_exit_3_and_records_nothing(tmp_path, fake_adapty):
    bin_dir, log = fake_adapty
    done, out = record(tmp_path, bin_dir, "ADAPTY_APP_ID=app-1\nADAPTY_EXPECTED_COMPANY=Synthetic Co\n")
    assert done.returncode == 3
    assert log.read_text().splitlines() == ["auth whoami --json"]
    assert not out
    assert "Other Co" not in done.stderr + done.stdout


def test_part_of_the_company_name_is_not_a_match(tmp_path, fake_adapty):
    bin_dir, log = fake_adapty
    done, out = record(tmp_path, bin_dir, "ADAPTY_APP_ID=app-1  # comment\nADAPTY_EXPECTED_COMPANY=other co\n")
    assert done.returncode == 3
    assert not out


def test_history_window_matches_live_reads():
    text = SCRIPT.read_text()
    assert "HISTORY_DAYS" in text and "2026-07-01" not in text
