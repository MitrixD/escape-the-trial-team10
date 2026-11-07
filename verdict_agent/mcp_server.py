"""Stdio MCP server with one tool, ab_test_verdict, returning the same JSON as the CLI."""
from mcp.server.mcpserver import MCPServer

from verdict_agent.service import safe_verdict

DESCRIPTION = (
    "Read-only verdict for an Adapty A/B test: can its leader be trusted yet, counting revenue that has not "
    "arrived (pending trials, future renewals). Call it before stopping a test or choosing a winner. "
    "Returns JSON only. When you explain it, use only numbers that appear in the JSON and state the verdict "
    "as given in `verdict`. Revenue fields in `arms` are USD per user; the renewals part includes expected "
    "refunds and can be negative."
)

server = MCPServer("verdict-agent")


@server.tool(name="ab_test_verdict", description=DESCRIPTION)
def ab_test_verdict(ab_test_id: str, horizon: int | None = None, replay: str | None = None) -> dict:
    return safe_verdict(ab_test_id=ab_test_id, horizon=horizon, replay=replay)


if __name__ == "__main__":
    server.run("stdio")
