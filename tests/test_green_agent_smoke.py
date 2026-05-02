import json
from pathlib import Path

import pytest
from a2a.utils import new_agent_text_message

from agent import Agent


ROOT = Path(__file__).parent.parent


class DummyUpdater:
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
async def test_green_agent_public_task_smoke(tmp_path):
    data_dir = tmp_path / "atlas_cache"
    req = {
        "participants": {"purple_agent": "http://unused.example.com"},
        "config": {
            "data_dir": str(data_dir),
            "task_dirs": [str(ROOT / "tasks_public" / "t001_zpeak_fit")],
            "task_overrides": {"t001_zpeak_fit": {"mode": "mock"}},
        },
    }

    updater = DummyUpdater()
    await Agent().run(new_agent_text_message(json.dumps(req)), updater)

    assert updater.rejected is None
    summary_artifacts = [artifact for artifact in updater.artifacts if artifact[0] == "Summary"]
    assert len(summary_artifacts) == 1
    assert len(summary_artifacts[0][1]) == 1

    run_dirs = list((data_dir / "runs").iterdir())
    assert len(run_dirs) == 1
    run_summary = json.loads((run_dirs[0] / "run_summary.json").read_text(encoding="utf-8"))
    assert run_summary["score_total"] == 1.0
    assert run_summary["score_max"] == 1.0

    task_dir = run_dirs[0] / "t001_zpeak_fit"
    expected = {
        "artifact_manifest.json",
        "fit_summary.json",
        "interpretation.md",
        "judge_input.json",
        "judge_output.json",
        "meta.json",
        "submission_bundle_raw.json",
        "submission_trace.json",
    }
    assert expected <= {path.name for path in task_dir.iterdir()}

    report = json.loads((task_dir / "judge_output.json").read_text(encoding="utf-8"))
    assert report["hard_checks_passed"] is True
    assert report["score_visibility"] == "public_only"
    assert report["final"] == {
        "total_score": 1.0,
        "max_score": 1.0,
        "normalized_score": 1.0,
    }
