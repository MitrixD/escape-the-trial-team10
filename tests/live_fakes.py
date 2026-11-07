import json
import pathlib
import subprocess

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "live"
APP = "app-under-test"
ONB_ID = "995b124f-9075-440d-83bb-20dbdf7d7fbb"
COMPANY = "Synthetic Team Company"
FLOW_A = "fc4f9fe6-5a00-4abe-aba0-f8c31839a21a"
FLOW_B = "776b28bb-1a9a-4610-948b-f74f7842a464"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class FakeRunner:
    def __init__(self, whoami: dict | None = None):
        self.calls: list[list[str]] = []
        self.whoami = whoami if whoami is not None else {"user": {"email": "dev@example.test"}, "company": {"title": COMPANY}}

    def __call__(self, cmd, capture_output=True, text=True, **kwargs):
        self.calls.append(list(cmd))
        args = cmd[1:]
        if args[:2] == ["auth", "whoami"]:
            out = json.dumps(self.whoami)
        elif args[:2] == ["ab-tests", "get"]:
            out = _fixture("ab_test_get.json")
        elif args[:3] == ["ab-tests", "metrics", "total"]:
            out = _fixture("ab_test_metrics_total.json")
        elif args[:2] == ["analytics", "funnel"]:
            out = _fixture("funnel_arm_1.json" if f"flow_id={FLOW_A}" in args else "funnel_arm_2.json")
        else:
            out = "{}"
        return subprocess.CompletedProcess(cmd, 0, out, "")
