import json
from pathlib import Path

import pytest
from a2a.types import DataPart
from a2a.utils import new_agent_text_message

from agent import Agent


ROOT = Path(__file__).parent.parent


class RecordingUpdater:
    def __init__(self):
        self.artifacts = []
        self.rejected = None
        self.completed = None

    async def update_status(self, state, message):
        pass

    async def add_artifact(self, parts, name):
        self.artifacts.append((name, parts))

    async def reject(self, message):
        self.rejected = message

    async def complete(self, message):
        self.completed = message


@pytest.mark.asyncio
async def test_public_contract_e2e_mock_run(tmp_path):
    req = {
        "participants": {"purple_agent": "http://unused.example.com"},
        "config": {
            "data_dir": str(tmp_path / "runs"),
            "task_dirs": [str(ROOT / "tasks_public" / "t001_zpeak_fit")],
            "task_overrides": {"t001_zpeak_fit": {"mode": "mock"}},
        },
    }

    updater = RecordingUpdater()
    await Agent().run(new_agent_text_message(json.dumps(req)), updater)

    assert updater.rejected is None
    assert updater.completed is not None
    summary_artifacts = [artifact for artifact in updater.artifacts if artifact[0] == "Summary"]
    assert len(summary_artifacts) == 1
    assert len(summary_artifacts[0][1]) == 2

    data_payloads = [
        part.root.data
        for _, parts in updater.artifacts
        for part in parts
        if isinstance(part.root, DataPart)
    ]
    task_payloads = [payload for payload in data_payloads if payload.get("task_id")]
    assert len(task_payloads) == 1
    assert task_payloads[0]["task_id"] == "t001_zpeak_fit"
    assert "tasks" not in task_payloads[0]

    run_dirs = list((Path(req["config"]["data_dir"]) / "runs").iterdir())
    assert len(run_dirs) == 1
    summary = json.loads((run_dirs[0] / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["score_total"] == 1.0
    assert summary["score_max"] == 1.0

    task_dir = Path(summary["run_dir"]) / "t001_zpeak_fit"
    judge_input = json.loads((task_dir / "judge_input.json").read_text(encoding="utf-8"))
    judge_output = json.loads((task_dir / "judge_output.json").read_text(encoding="utf-8"))

    assert judge_input["submission_trace"] == {"path": "submission_trace.json"}
    assert judge_output["score_visibility"] == "public_only"
    assert judge_output["public_scores"]["contract_pass"] == 1.0
