"""Stdio MCP server with one tool, ab_test_verdict, returning the same JSON as the CLI."""
from mcp.server.mcpserver import MCPServer

from verdict_agent.service import safe_verdict

DESCRIPTION = (
    "Read-only verdict for an Adapty A/B test: can its leader be trusted yet, counting revenue that has not "
    "arrived (pending trials, future renewals). Call it before stopping a test or choosing a winner. "
    "Returns JSON only. When you explain it, use only numbers that appear in the JSON and state the verdict "
    "as given in `verdict`. Revenue fields in `arms` and `expected_gap_per_user` are USD per user; the renewals "
    "part includes expected refunds and can be negative. Pass `horizon` as the number of days the test goal names "
    "(for example \"60-day revenue\" -> 60); if the goal names no number of days, omit it. USD values in `money` are "
    "totals for the test's traffic, not per user; `after_days` is how long the shipped arm serves that traffic after "
    "the stop (180 when omitted). `next_action` with `next_action_basis` \"money\" means the leader is not proven, "
    "but waiting until `come_back_on` is expected to cost more than shipping it now; basis \"horizon\" means the "
    "test has passed its horizon, so there is nothing left to wait for. `next_action` \"fix_test\" (basis \"health\") "
    "means the split is broken (`health`: a sample ratio mismatch or a dead arm): do not ship any variant."
)

server = MCPServer("verdict-agent")


@server.tool(name="ab_test_verdict", description=DESCRIPTION)
def ab_test_verdict(ab_test_id: str, horizon: int | None = None, replay: str | None = None,
                    app_id: str | None = None, after_days: int | None = None) -> dict:
    return safe_verdict(ab_test_id=ab_test_id, horizon=horizon, replay=replay, app_id=app_id, after_days=after_days)


if __name__ == "__main__":
    server.run("stdio")
