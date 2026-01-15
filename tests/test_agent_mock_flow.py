import json
import pytest
from pathlib import Path
import yaml

from a2a.types import Message, Part, TextPart

from agent import Agent
from tasks.task_spec import GreenConfig

class FakeUpdater:
    def __init__(self):
        self.status_updates = []
        self.artifacts = []
        self.rejected = None

    async def update_status(self, state, message):
        self.status_updates.append((state, message))

    async def add_artifact(self, parts, name):
        self.artifacts.append((name, parts))

    async def reject(self, message):
        self.rejected = message


@pytest.mark.asyncio
async def test_agent_runs_two_mock_tasks(monkeypatch, tmp_path):
    # Patch the symbol as imported inside agent.py:
    import agent as agent_module

    def _fake_download(cfg, task):
        return {
            "n_files": 1,
            "local_paths": ["/tmp/fake.root"],
            "dataset": getattr(task, "dataset", "data"),
            "skim": getattr(task, "skim", "skim"),
        }
    
    # We also mock ensure_atlas_open_data_downloaded because that is what agent.py uses now
    monkeypatch.setattr(agent_module, "ensure_atlas_open_data_downloaded", _fake_download)

    # create mock tasks in tmp_path
    d1 = tmp_path / "task1"
    d1.mkdir()
    (d1 / "task_spec.yaml").write_text(yaml.dump({
        "id": "t1",
        "type": "zpeak_fit",
        "mode": "mock",
        "needs_data": True,
        "skim": "2muons",
        "rubric_path": "rubric.yaml"
    }))
    (d1 / "rubric.yaml").write_text(yaml.dump({"total": 100, "llm_checks": []}))

    d2 = tmp_path / "task2"
    d2.mkdir()
    (d2 / "task_spec.yaml").write_text(yaml.dump({
        "id": "t2",
        "type": "hyy_analysis",
        "mode": "mock",
        "needs_data": True,
        "skim": "2gammas",
        "rubric_path": "rubric.yaml"
    }))
    (d2 / "rubric.yaml").write_text(yaml.dump({"total": 100, "llm_checks": []}))

    cfg = GreenConfig(
        data_dir=str(tmp_path / "data"),
        release="2025e-13tev-beta",
        task_dirs=[str(d1), str(d2)],
    )

    req = {"participants": {}, "config": cfg.model_dump()}

    msg = Message(
        messageId="test-msg-1",
        role="user",
        parts=[Part(root=TextPart(text=json.dumps(req)))]
    )
    updater = FakeUpdater()

    a = Agent()
    await a.run(msg, updater)

    if updater.rejected:
        print("Rejected:", updater.rejected)

    assert updater.rejected is None

    names = [name for name, _ in updater.artifacts]
    assert "Result-t1" in names
    assert "Result-t2" in names
    assert "Summary" in names
