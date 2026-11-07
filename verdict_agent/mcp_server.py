"""Stdio MCP server with one tool, ab_test_verdict, returning the same JSON as the CLI."""
from mcp.server.mcpserver import MCPServer

from verdict_agent.cli import safe_verdict

DESCRIPTION = (
    "Read-only verdict for an Adapty A/B test. Call it before stopping a test or choosing a winner. "
    "Returns JSON only. When you explain it, use only numbers that appear in the JSON, state the verdict "
    "as given in `verdict`, and say whether the data is live or offline."
    " Revenue fields in `arms` are USD per user, not totals; `money_at_stake_usd` is a total."
)

server = MCPServer("verdict-agent")


@server.tool(name="ab_test_verdict", description=DESCRIPTION)
def ab_test_verdict(
    ab_test_id: str | None = None,
    offline_test: str | None = None,
    day: int = 14,
    traffic: int = 100,
    horizon: int | None = None,
) -> dict:
    return safe_verdict(
        ab_test_id=ab_test_id, offline_test=offline_test, day=day, traffic=traffic, horizon=horizon,
    )


if __name__ == "__main__":
    server.run("stdio")
