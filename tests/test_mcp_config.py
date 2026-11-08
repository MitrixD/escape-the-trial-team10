import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_example_config_sets_pythonpath():
    server = json.loads((REPO / ".mcp.json.example").read_text())["mcpServers"]["verdict-agent"]
    assert server["env"]["PYTHONPATH"] == "<absolute path to this repo>"


def test_written_config_survives_hash_and_spaces_in_the_path(tmp_path):
    repo = "/tmp/odd # dir/with space"
    out = tmp_path / ".mcp.json"
    subprocess.run([sys.executable, str(REPO / "scripts" / "mcp_config.py"), repo, str(out)], check=True)
    server = json.loads(out.read_text())["mcpServers"]["verdict-agent"]
    assert server == {"command": f"{repo}/.venv/bin/python", "args": ["-m", "verdict_agent.mcp_server"],
                      "cwd": repo, "env": {"PYTHONPATH": repo}}


def test_server_module_loads_from_the_root_folder():
    done = subprocess.run([sys.executable, "-c", "import verdict_agent.mcp_server"], cwd="/",
                          env={"PYTHONPATH": str(REPO)}, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
