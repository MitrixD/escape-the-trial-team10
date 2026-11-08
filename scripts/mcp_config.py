"""Write .mcp.json for the verdict-agent server: scripts/mcp_config.py <repo> <output file>."""
import json
import sys

repo, out = sys.argv[1], sys.argv[2]
server = {"command": f"{repo}/.venv/bin/python", "args": ["-m", "verdict_agent.mcp_server"],
          "cwd": repo, "env": {"PYTHONPATH": repo}}
with open(out, "w") as f:
    json.dump({"mcpServers": {"verdict-agent": server}}, f, indent=2)
    f.write("\n")
