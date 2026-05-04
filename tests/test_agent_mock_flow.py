import json
from pathlib import Path

import pytest
from a2a.types import DataPart
from a2a.utils import new_agent_text_message

from agent import Agent


ROOT = Path(__file__).parent.parent


class FakeUpdater:
    def __init__(self):
        self.status_updates = []
        self.artifacts = []
        self.rejected = None
        self.completed = None

    async def update_status(self, state, message):
        self.status_updates.append((state, message))

    async def add_artifact(self, parts, name):
        self.artifacts.append((name, parts))

    async def reject(self, message):
        self.rejected = message

    async def complete(self, message):
        self.completed = message


@pytest.mark.asyncio
async def test_agent_runs_public_mock_tasks(monkeypatch, tmp_path):
    monkeypatch.setenv("GREEN_SECRETS_JSON", "")

    req = {
        "participants": {"purple_agent": "http://unused.example.com"},
        "config": {
            "data_dir": str(tmp_path / "data"),
            "task_dirs": [
                str(ROOT / "tasks_public" / "t001_zpeak_fit"),
                str(ROOT / "tasks_public" / "t002_hyy_v5_l1"),
            ],
            "task_overrides": {
                "t001_zpeak_fit": {"mode": "mock"},
                "t002_hyy_v5_l1": {"mode": "mock"},
            },
        },
    }

    updater = FakeUpdater()
    await Agent().run(new_agent_text_message(json.dumps(req)), updater)

    assert updater.rejected is None
    names = [name for name, _ in updater.artifacts]
    assert "Result-t001_zpeak_fit" in names
    assert "Result-t002_hyy_v5_l1" in names
    assert "Summary" in names
    summary_artifact = [artifact for artifact in updater.artifacts if artifact[0] == "Summary"][0]
    assert len(summary_artifact[1]) == 2
    summary_payload = summary_artifact[1][1].root.data
    assert summary_payload["llm"]["solver"]["configured"] == {
        "backend": "agent_1_oh",
        "model": "gpt-5",
        "source": "default",
    }

    data_payloads = [
        part.root.data
        for _, parts in updater.artifacts
        for part in parts
        if isinstance(part.root, DataPart)
    ]
    task_payloads = [payload for payload in data_payloads if payload.get("task_id")]
    assert {payload.get("task_id") for payload in task_payloads} == {"t001_zpeak_fit", "t002_hyy_v5_l1"}
    assert all("tasks" not in payload for payload in task_payloads)
    assert all(payload.get("solver_backend") == "agent_1_oh" for payload in task_payloads)
    assert all(payload["llm"]["solver"]["configured"]["model"] == "gpt-5" for payload in task_payloads)
    assert all("purple_agent_runtime_seconds" in payload for payload in task_payloads)
    assert all(payload.get("timing", {}).get("purple_agent_used") is False for payload in task_payloads)

    run_dirs = list((tmp_path / "data" / "runs").iterdir())
    assert len(run_dirs) == 1
    for task_id in ["t001_zpeak_fit", "t002_hyy_v5_l1"]:
        task_dir = run_dirs[0] / task_id
        assert (task_dir / "submission_bundle_raw.json").exists()
        assert (task_dir / "submission_trace.json").exists()
        report = json.loads((task_dir / "judge_output.json").read_text(encoding="utf-8"))
        assert report["status"] == "public_ok_hidden_unavailable"
        assert report["public_scores"]["contract_pass"] == 1.0
        assert report["hidden_scores"]["status"] == "unavailable"
        assert report["final"]["normalized_score"] == 1.0
