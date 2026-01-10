import json
import pytest

from a2a.types import Message, Part, TextPart

from agent import Agent
from tasks.task_spec import GreenConfig, ZPeakFitTaskSpec, HyyAnalysisTaskSpec


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
async def test_agent_runs_two_mock_tasks(monkeypatch):
    # Patch the symbol as imported inside agent.py:
    # agent.py: from utils.atlas_download import ensure_data_downloaded
    import agent as agent_module

    def _fake_download(cfg, task):
        return {
            "n_files": 1,
            "local_paths": ["/tmp/fake.root"],
            "dataset": getattr(task, "dataset", "data"),
            "skim": getattr(task, "skim", "skim"),
        }

    monkeypatch.setattr(agent_module, "ensure_data_downloaded", _fake_download)

    cfg = GreenConfig(
        data_dir="/tmp/atlas_cache",
        release="2025e-13tev-beta",
        tasks=[
            ZPeakFitTaskSpec(id="t1", mode="mock", needs_data=True),
            HyyAnalysisTaskSpec(id="t2", mode="mock", needs_data=True),
        ],
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

    assert updater.rejected is None

    names = [name for name, _ in updater.artifacts]
    assert "Result-t1" in names
    assert "Result-t2" in names
    assert "Summary" in names
