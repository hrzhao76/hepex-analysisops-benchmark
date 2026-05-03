import json
from pathlib import Path

import pytest

from engine.benchmark_engine import BenchmarkEngine
from engine.run_models import EvalRequest
from utils.mock_traces import get_mock_bundle


ROOT = Path(__file__).parent.parent
ZPEAK_TASK_DIR = ROOT / "tasks_public" / "t001_zpeak_fit"
HYY_TASK_DIR = ROOT / "tasks_public" / "t002_hyy_v5_l1"


class FakeTransport:
    def __init__(self, response_bundle: dict | None = None):
        self.payloads = []
        self.response_bundle = response_bundle

    async def request_submission_bundle(self, payload):
        self.payloads.append(payload)
        bundle = self.response_bundle or get_mock_bundle(payload["task_type"], payload["task_id"])
        return json.dumps(bundle)


class FakeObserver:
    def __init__(self):
        self.statuses = []
        self.task_results = []
        self.summaries = []

    async def status(self, text):
        self.statuses.append(text)

    async def task_result(self, name, summary, report):
        self.task_results.append((name, summary, report))

    async def summary(self, text, overall):
        self.summaries.append((text, overall))


def eval_request(config: dict) -> EvalRequest:
    return EvalRequest.model_validate(
        {
            "participants": {"purple_agent": "http://example.com"},
            "config": config,
        }
    )


@pytest.mark.asyncio
async def test_benchmark_engine_mock_run_materializes_public_bundle(tmp_path):
    engine = BenchmarkEngine()
    observer = FakeObserver()
    request = eval_request(
        {
            "data_dir": str(tmp_path / "data"),
            "task_dirs": [str(ZPEAK_TASK_DIR)],
            "task_overrides": {"t001_zpeak_fit": {"mode": "mock"}},
        }
    )

    result = await engine.run(request, FakeTransport(), observer)

    task_dir = Path(result.overall["run_dir"]) / "t001_zpeak_fit"
    assert (task_dir / "submission_bundle_raw.json").exists()
    assert (task_dir / "fit_summary.json").exists()
    assert (task_dir / "judge_output.json").exists()
    run_summary = json.loads((Path(result.overall["run_dir"]) / "run_summary.json").read_text(encoding="utf-8"))
    assert run_summary == result.overall
    assert result.overall["score_total"] == 1.0
    assert observer.task_results[0][0] == "Result-t001_zpeak_fit"


@pytest.mark.asyncio
async def test_benchmark_engine_real_mode_calls_solver_transport_with_contract(tmp_path):
    engine = BenchmarkEngine()
    observer = FakeObserver()
    transport = FakeTransport()
    request = eval_request(
        {
            "data_dir": str(tmp_path / "data"),
            "task_dirs": [str(ZPEAK_TASK_DIR)],
        }
    )

    await engine.run(request, transport, observer)

    assert len(transport.payloads) == 1
    payload = transport.payloads[0]
    assert payload["task_id"] == "t001_zpeak_fit"
    assert payload["solver_backend"] == "agent_1_oh"
    assert payload["constraints"]["response_format"] == "submission_bundle_v1"
    assert "solver_backend" not in payload["constraints"]
    assert payload["submission_contract"]["required_outputs"][0]["canonical_filename"] == "fit_summary.json"
    assert payload["data"]["work_dir"].endswith("/t001_zpeak_fit/solver_work")
    assert payload["data"]["output_dir"] == payload["data"]["work_dir"]
    assert Path(payload["data"]["work_dir"]).is_dir()


@pytest.mark.asyncio
async def test_benchmark_engine_passes_solver_backend_from_eval_request(tmp_path):
    engine = BenchmarkEngine()
    observer = FakeObserver()
    transport = FakeTransport()
    request = eval_request(
        {
            "data_dir": str(tmp_path / "data"),
            "task_dirs": [str(ZPEAK_TASK_DIR)],
            "solver_backend": "agent_2_xxx",
        }
    )

    await engine.run(request, transport, observer)

    payload = transport.payloads[0]
    assert payload["solver_backend"] == "agent_2_xxx"
    assert "solver_backend" not in payload["constraints"]
    assert any("Solver backend default: agent_2_xxx" in status for status in observer.statuses)


@pytest.mark.asyncio
async def test_benchmark_engine_accepts_top_level_solver_backend(tmp_path):
    engine = BenchmarkEngine()
    observer = FakeObserver()
    transport = FakeTransport()
    request = EvalRequest.model_validate(
        {
            "participants": {"purple_agent": "http://example.com"},
            "solver_backend": "agent_2_top",
            "config": {
                "data_dir": str(tmp_path / "data"),
                "task_dirs": [str(ZPEAK_TASK_DIR)],
            },
        }
    )

    await engine.run(request, transport, observer)

    assert transport.payloads[0]["solver_backend"] == "agent_2_top"


@pytest.mark.asyncio
async def test_persisted_payloads_do_not_emit_redundant_null_or_solver_backend_fields(tmp_path):
    engine = BenchmarkEngine()
    observer = FakeObserver()
    transport = FakeTransport()
    request = eval_request(
        {
            "data_dir": str(tmp_path / "data"),
            "task_dirs": [str(ZPEAK_TASK_DIR)],
            "solver_backend": "agent_1_oh",
            "task_overrides": {"t001_zpeak_fit": {"mode": "call_white", "solver_backend": None}},
        }
    )

    result = await engine.run(request, transport, observer)

    run_dir = Path(result.overall["run_dir"])
    eval_payload = json.loads((run_dir / "eval_request.json").read_text(encoding="utf-8"))
    green_config = json.loads((run_dir / "green_config.json").read_text(encoding="utf-8"))
    judge_input = json.loads((run_dir / "t001_zpeak_fit" / "judge_input.json").read_text(encoding="utf-8"))
    purple_request = json.loads((run_dir / "t001_zpeak_fit" / "purple_request.json").read_text(encoding="utf-8"))

    assert eval_payload["config"]["solver_backend"] == "agent_1_oh"
    assert "solver_backend" not in eval_payload
    assert "solver_backend" not in green_config["task_overrides"]["t001_zpeak_fit"]
    assert "solver_backend" not in judge_input["task_spec"]
    assert purple_request["solver_backend"] == "agent_1_oh"
    assert "solver_backend" not in purple_request["constraints"]


@pytest.mark.asyncio
async def test_benchmark_engine_applies_overrides_and_skips_disabled_task(tmp_path):
    engine = BenchmarkEngine()
    observer = FakeObserver()
    request = eval_request(
        {
            "data_dir": str(tmp_path / "data"),
            "task_dirs": [str(ZPEAK_TASK_DIR), str(HYY_TASK_DIR)],
            "task_overrides": {
                "t001_zpeak_fit": {"mode": "mock"},
                "t002_hyy_v5_l1": {"enabled": False},
            },
        }
    )

    result = await engine.run(request, FakeTransport(), observer)

    assert len(result.overall["tasks"]) == 1
    assert result.overall["tasks"][0]["task_id"] == "t001_zpeak_fit"
    assert result.overall["score_max"] == 1.0
    assert any("Skipped" in status for status in observer.statuses)


@pytest.mark.asyncio
async def test_benchmark_engine_summary_aggregates_two_public_mock_tasks(monkeypatch, tmp_path):
    monkeypatch.setenv("GREEN_SECRETS_JSON", "")

    engine = BenchmarkEngine()
    observer = FakeObserver()
    request = eval_request(
        {
            "data_dir": str(tmp_path / "data"),
            "task_dirs": [str(ZPEAK_TASK_DIR), str(HYY_TASK_DIR)],
            "task_overrides": {
                "t001_zpeak_fit": {"mode": "mock"},
                "t002_hyy_v5_l1": {"mode": "mock"},
            },
        }
    )

    result = await engine.run(request, FakeTransport(), observer)

    assert result.overall["score_total"] == 2.0
    assert result.overall["score_max"] == 2.0
    assert (Path(result.overall["run_dir"]) / "run_summary.json").exists()
    assert len(observer.summaries) == 1
