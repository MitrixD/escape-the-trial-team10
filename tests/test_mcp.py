import asyncio
from pathlib import Path

from verdict_agent import service
from verdict_agent.mcp_server import DESCRIPTION, ab_test_verdict, server

ONBOARDING = Path(__file__).parent / "fixtures" / "live" / "995b124f-9075-440d-83bb-20dbdf7d7fbb"

EXPECTED_DESCRIPTION = (
    "Read-only verdict for an Adapty A/B test: can its leader be trusted yet, counting revenue that has not "
    "arrived (pending trials, future renewals). Call it before stopping a test or choosing a winner. "
    "Returns JSON only. When you explain it, use only numbers that appear in the JSON and state the verdict "
    "as given in `verdict`. Revenue fields in `arms` and `expected_gap_per_user` are USD per user; the renewals "
    "part includes expected refunds and can be negative. Pass `horizon` as the number of days the test goal names "
    "(for example \"60-day revenue\" -> 60); if the goal names no number of days, omit it."
)


def test_handler_matches_service():
    kwargs = {"ab_test_id": ONBOARDING.name, "horizon": None, "replay": str(ONBOARDING), "app_id": None}
    assert ab_test_verdict(**kwargs) == service.verdict(**kwargs)


def test_handler_returns_error_dict():
    assert "error" in ab_test_verdict(ab_test_id="x", horizon=0, replay=str(ONBOARDING))


def test_single_tool_with_exact_description():
    assert DESCRIPTION == EXPECTED_DESCRIPTION
    tools = asyncio.run(server.list_tools())
    assert [t.name for t in tools] == ["ab_test_verdict"]
    assert tools[0].description == EXPECTED_DESCRIPTION
    assert set(tools[0].input_schema["properties"]) == {"ab_test_id", "horizon", "replay", "app_id"}


def test_description_phrases():
    for phrase in ("before stopping a test", "only numbers that appear in the JSON", "USD per user", "can be negative",
                   "expected_gap_per_user", "number of days the test goal names"):
        assert phrase in DESCRIPTION


def test_handler_passes_app_id_to_the_service(monkeypatch):
    seen = {}
    monkeypatch.setattr("verdict_agent.mcp_server.safe_verdict", lambda **kw: seen.update(kw) or {})
    ab_test_verdict(ab_test_id="t", app_id="CALL-APP")
    assert seen == {"ab_test_id": "t", "horizon": None, "replay": None, "app_id": "CALL-APP"}
