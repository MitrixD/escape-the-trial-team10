import asyncio

import pytest

import verdict_agent.service as service
from verdict_agent.mcp_server import DESCRIPTION, ab_test_verdict, server

SETTINGS = "Settings: upgrade vs lifetime anchor"
EXPECTED_DESCRIPTION = (
    "Read-only verdict for an Adapty A/B test. Call it before stopping a test or choosing a winner. "
    "Returns JSON only. When you explain it, use only numbers that appear in the JSON, state the verdict "
    "as given in `verdict`, and say whether the data is live or offline."
    " Revenue fields in `arms` are USD per user, not totals; `money_at_stake_usd` is a total."
    " The renewals part includes expected refunds and can be negative."
)


@pytest.mark.dataset
def test_tool_matches_service(tmp_path, monkeypatch, dataset_path):
    path = tmp_path / ".env"
    path.write_text(f"VERDICT_DATASET={dataset_path}\n")
    monkeypatch.setattr(service, "ENV_PATH", path)
    kwargs = {"offline_test": SETTINGS, "day": 14, "traffic": 100, "horizon": 90}
    out = ab_test_verdict(**kwargs)
    assert out == service.verdict(**kwargs)
    assert out["horizon_source"] == "parameter" and out["source"] == "offline"


def test_tool_returns_error_dict():
    assert ab_test_verdict(offline_test=SETTINGS, horizon=365) == {"error": "horizon must be between 1 and 120 days"}
    assert "error" in ab_test_verdict()


def test_single_tool_with_exact_description():
    assert DESCRIPTION == EXPECTED_DESCRIPTION
    tools = asyncio.run(server.list_tools())
    assert [t.name for t in tools] == ["ab_test_verdict"]
    tool = tools[0]
    assert tool.description == EXPECTED_DESCRIPTION
    assert set(tool.input_schema["properties"]) == {"ab_test_id", "offline_test", "day", "traffic", "horizon"}


def test_description_states_revenue_units():
    assert "USD per user" in DESCRIPTION


def test_description_says_renewals_can_be_negative():
    assert DESCRIPTION.endswith(" The renewals part includes expected refunds and can be negative.")
