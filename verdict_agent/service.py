"""One entry point for the CLI and the MCP tool: live verdict by A/B test ID or offline verdict by test name."""
from pathlib import Path

from verdict_agent.live import ENV_PATH, environment, run_live
from verdict_agent.offline import run_offline
from verdict_agent.verdict import check_horizon


def verdict(
    ab_test_id: str | None = None,
    offline_test: str | None = None,
    day: int = 14,
    traffic: int = 100,
    horizon: int | None = None,
) -> dict:
    if bool(ab_test_id) == bool(offline_test):
        raise ValueError("pass exactly one of ab_test_id (live) or offline_test (offline)")
    check_horizon(horizon)
    if ab_test_id:
        return run_live(ab_test_id, env_path=ENV_PATH, horizon=horizon)
    dataset = environment(ENV_PATH).get("VERDICT_DATASET", "")
    if not dataset:
        raise ValueError("VERDICT_DATASET is not set; it is needed for offline mode")
    return run_offline(Path(dataset), offline_test, day, traffic, horizon=horizon)
