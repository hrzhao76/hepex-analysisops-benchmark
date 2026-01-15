import asyncio
import json
import os
from pathlib import Path

import pytest

from a2a.utils import new_agent_text_message
from agent import Agent


class DummyUpdater:
    """
    Minimal TaskUpdater stand-in that records what the agent emits.
    """
    def __init__(self):
        self.status_updates = []
        self.artifacts = []
        self.rejected = None
        self.completed = None

    async def update_status(self, state, message):
        # message is a2a Message; capture text for debugging
        txt = ""
        try:
            txt = message.parts[0].root.text
        except Exception:
            txt = str(message)
        self.status_updates.append((state, txt))

    async def add_artifact(self, parts, name: str):
        # Capture artifact name + parts
        self.artifacts.append((name, parts))

    async def reject(self, message):
        try:
            self.rejected = message.parts[0].root.text
        except Exception:
            self.rejected = str(message)

    async def complete(self, message):
        try:
            self.completed = message.parts[0].root.text
        except Exception:
            self.completed = str(message)


@pytest.mark.asyncio
async def test_green_agent_smoke(tmp_path, monkeypatch):
    """
    Smoke test:
    - Agent accepts EvalRequest JSON
    - Runs at least 1 mock task (without downloading data)
    - Emits per-task artifact + Summary
    - Writes run_dir with expected files
    """

    # Make runs write into tmp_path (avoid touching /tmp or your real cache)
    # Your agent resolves data_dir from config, so just pass tmp_path as data_dir.
    data_dir = tmp_path / "atlas_cache"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Mock data download to avoid network/large files
    import agent as agent_module
    def _fake_download(**kwargs): # handle all args
         return {
            "n_files": 1,
            "local_paths": ["/tmp/fake.root"],
            "dataset": kwargs.get("dataset", "data"),
            "skim": kwargs.get("skim", "skim"),
         }
    monkeypatch.setattr(agent_module, "ensure_atlas_open_data_downloaded", _fake_download)

    # Create mock task in tmp_path
    spec_dir = tmp_path / "specs" / "zpeak_fit"
    spec_dir.mkdir(parents=True, exist_ok=True)
    
    import yaml
    (spec_dir / "task_spec.yaml").write_text(yaml.dump({
        "id": "t001_zpeak_fit",
        "type": "zpeak_fit",
        "mode": "mock",
        "needs_data": True,
        "skim": "2muons",
        "rubric_path": "rubric.yaml"
    }))
    (spec_dir / "rubric.yaml").write_text(yaml.dump({
        "total": 100,
        "gates": [{"id":"g1", "type":"required_fields", "required_fields":["status"]}],
        "rule_checks": []
    }))

    # Build a minimal platform request
    req = {
        "participants": {},  # no white_agent needed in mock mode
        "config": {
            "data_dir": str(data_dir),
            "task_dirs": [str(spec_dir)],
        },
    }

    # Construct the A2A text message
    msg = new_agent_text_message(json.dumps(req))

    agent = Agent()
    updater = DummyUpdater()

    await agent.run(msg, updater)

    # Assertions: should not reject
    assert updater.rejected is None, f"Agent rejected request: {updater.rejected}"

    # Should complete (if your agent calls complete; otherwise allow None)
    # If you decided not to call complete(), comment this out.
    # assert updater.completed is not None

    # Should emit at least one per-task artifact + Summary
    artifact_names = [name for name, _ in updater.artifacts]
    assert any(n.startswith("Result-") for n in artifact_names), f"No Result-* artifacts: {artifact_names}"
    assert "Summary" in artifact_names, f"No Summary artifact: {artifact_names}"

    # Find Summary DataPart to locate run_dir (agent writes overall with run_dir)
    # We can also just search filesystem under data_dir/runs
    runs_root = data_dir / "runs"
    assert runs_root.exists(), f"runs directory not created at: {runs_root}"

    # There should be exactly one run_id directory
    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    assert len(run_dirs) == 1, f"Expected 1 run dir, got {len(run_dirs)}: {run_dirs}"
    run_dir = run_dirs[0]

    # Task directory should exist
    task_dir = run_dir / "t001_zpeak_fit"
    assert task_dir.exists(), f"Task run dir missing: {task_dir}"

    # Expected files
    expected = {
        "meta.json",
        "submission_trace.json",
        "judge_input.json",
        "judge_output.json",
    }
    found = {p.name for p in task_dir.iterdir() if p.is_file()}
    missing = expected - found
    assert not missing, f"Missing files in {task_dir}: {missing}, found={found}"


    # ---- content asserts ----
    meta = json.loads((task_dir / "meta.json").read_text(encoding="utf-8"))
    trace = json.loads((task_dir / "submission_trace.json").read_text(encoding="utf-8"))
    out = json.loads((task_dir / "judge_output.json").read_text(encoding="utf-8"))

    # meta basics
    assert meta.get("task_id") == "t001_zpeak_fit"
    assert meta.get("task_type") == "zpeak_fit"
    assert meta.get("mode") == "mock"

    # trace basics
    assert trace.get("task_id") == "t001_zpeak_fit"
    assert trace.get("status") in (None, "ok", "success", "error")  # be tolerant while schema evolves

    # judge output basics
    assert out.get("task_id") == "t001_zpeak_fit"
    assert out.get("type") == "zpeak_fit"

    final = out.get("final")
    assert isinstance(final, dict), f"final missing or not dict: {final}"

    for k in ("total_score", "max_score", "normalized_score"):
        assert k in final, f"final.{k} missing: final={final}"

    total = float(final["total_score"])
    max_score = float(final["max_score"])
    norm = float(final["normalized_score"])

    assert max_score > 0.0, f"max_score must be > 0, got {max_score}"
    assert 0.0 - 1e-9 <= norm <= 1.0 + 1e-9, f"normalized_score out of [0,1]: {norm}"
    assert 0.0 - 1e-9 <= total <= max_score + 1e-6, f"total_score {total} exceeds max_score {max_score}"

    # Optional sanity: normalized ~= total/max_score (within tolerance)
    assert abs(norm - (total / max_score)) < 1e-6, f"normalized mismatch: {norm} vs {total/max_score}"
