from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
import yaml

from a2a.utils import new_agent_text_message

from agent import Agent, AgentSolverTransport
from engine.benchmark_engine import BenchmarkEngine
from engine.contract_validator import validate_submission_dir
from engine.evaluation import EvaluationEngine
from engine.input_access import InputAccessError, resolve_input_access
from engine.package_loader import load_private_l1_rubric, load_submission_contract
from engine.run_models import EvalRequest
from engine.secret_store import SecretStore
from engine.submission_bundle import SubmissionBundleError, parse_submission_bundle
from tasks.task_spec import GreenConfig, load_task_spec
from utils.mock_private_rubrics import hyy_l1_private_rubric


TASK_DIR = Path(__file__).parent.parent / "tasks_public" / "t002_hyy_v5_l1"
ZPEAK_TASK_DIR = Path(__file__).parent.parent / "tasks_public" / "t001_zpeak_fit"


def sample_submission_bundle() -> dict:
    return {
        "status": "ok",
        "artifacts": {
            "diphoton_mass_spectrum.json": {
                "bin_edges": [100.0, 101.0, 102.0],
                "bin_counts": [4, 7],
                "bin_uncertainties": [2.0, 2.6458],
            },
            "diphoton_fit_summary.json": {
                "signal_model_family": "gaussian",
                "background_model_family": "polynomial",
                "fit_range": [100.0, 160.0],
                "signal_peak_position": 125.1,
            },
            "data_minus_background.json": {
                "bin_centers": [124.5, 125.5],
                "residual_counts": [0.2, 1.7],
                "residual_uncertainties": [0.5, 0.6],
            },
            "interpretation.md": "A Higgs-like excess is observed near 125.1 GeV in the diphoton spectrum.",
            "submission_trace.json": {
                "workflow_stages": [
                    {"stage_id": "data_loading", "order_index": 1, "status": "ok", "depends_on": []},
                    {"stage_id": "event_selection", "order_index": 2, "status": "ok", "depends_on": ["data_loading"]},
                    {"stage_id": "diphoton_mass_construction", "order_index": 3, "status": "ok", "depends_on": ["event_selection"]},
                    {"stage_id": "spectrum_histogramming", "order_index": 4, "status": "ok", "depends_on": ["diphoton_mass_construction"]},
                    {"stage_id": "uncertainty_assignment", "order_index": 5, "status": "ok", "depends_on": ["spectrum_histogramming"]},
                    {"stage_id": "spectrum_fitting", "order_index": 6, "status": "ok", "depends_on": ["uncertainty_assignment"]},
                    {"stage_id": "signal_interpretation", "order_index": 7, "status": "ok", "depends_on": ["spectrum_fitting"]},
                ],
                "baseline_assumptions_used": [
                    "photon indices 0 and 1 correspond to the ordered leading/subleading pair",
                ],
                "object_definition": {
                    "type": "photon_pair",
                    "multiplicity": 2,
                    "ordering_principle": "leading_subleading_photon_pair",
                    "baseline_assumption": {
                        "leading_photon_index": 0,
                        "subleading_photon_index": 1,
                    },
                },
                "cuts_applied": [
                    {"cut_id": "at_least_two_photons", "applies_to": "event", "variable": "photon_count", "operator": ">=", "value": 2, "applied": True},
                    {"cut_id": "leading_photon_tight_id", "applies_to": "leading_photon", "variable": "photon_isTightID", "operator": "==", "value": True, "applied": True},
                    {"cut_id": "subleading_photon_tight_id", "applies_to": "subleading_photon", "variable": "photon_isTightID", "operator": "==", "value": True, "applied": True},
                    {"cut_id": "leading_photon_pt", "applies_to": "leading_photon", "variable": "photon_pt", "operator": ">", "value": 50.0, "applied": True},
                    {"cut_id": "subleading_photon_pt", "applies_to": "subleading_photon", "variable": "photon_pt", "operator": ">", "value": 30.0, "applied": True},
                    {"cut_id": "leading_photon_isolation", "applies_to": "leading_photon", "variable": "photon_ptcone20", "operator": "<", "value": 0.055, "depends_on": ["photon_ptcone20", "photon_pt"], "applied": True},
                    {"cut_id": "subleading_photon_isolation", "applies_to": "subleading_photon", "variable": "photon_ptcone20", "operator": "<", "value": 0.055, "depends_on": ["photon_ptcone20", "photon_pt"], "applied": True},
                    {"cut_id": "leading_photon_eta_transition_veto", "applies_to": "leading_photon", "variable": "abs_photon_eta", "operator": "interval_veto", "value": [1.37, 1.52], "interval": [1.37, 1.52], "applied": True},
                    {"cut_id": "subleading_photon_eta_transition_veto", "applies_to": "subleading_photon", "variable": "abs_photon_eta", "operator": "interval_veto", "value": [1.37, 1.52], "interval": [1.37, 1.52], "applied": True},
                    {"cut_id": "diphoton_mass_nonzero", "applies_to": "diphoton_pair", "variable": "m_yy", "operator": "!=", "value": 0.0, "applied": True},
                    {"cut_id": "leading_photon_pt_over_m_yy", "applies_to": "leading_photon", "variable": "photon_pt_over_m_yy", "operator": ">", "value": 0.35, "applied": True},
                    {"cut_id": "subleading_photon_pt_over_m_yy", "applies_to": "subleading_photon", "variable": "photon_pt_over_m_yy", "operator": ">", "value": 0.35, "applied": True},
                ],
                "derived_observables": [
                    {"name": "abs_photon_eta", "depends_on": ["photon_eta"]},
                    {"name": "m_yy", "depends_on": ["photon_pt", "photon_eta", "photon_phi", "photon_e"]},
                    {"name": "photon_pt_over_m_yy", "depends_on": ["photon_pt", "m_yy"]},
                ],
                "observable_constructed": {
                    "name": "m_yy",
                    "inputs": ["photon_pt", "photon_eta", "photon_phi", "photon_e"],
                    "formula_summary": "invariant mass of the first two photon four-vectors",
                },
                "primary_observable": {
                    "name": "m_yy",
                    "inputs": ["photon_pt", "photon_eta", "photon_phi", "photon_e"],
                    "construction": "invariant_mass_of_first_two_photon_four_vectors",
                },
                "histogram_definition": {
                    "observable": "m_yy",
                    "range": [100.0, 160.0],
                    "bin_width": 1.0,
                    "uncertainty_model": "sqrt_n_statistical_uncertainty",
                },
                "fit_model_family_used": {
                    "signal": "gaussian",
                    "background": "polynomial",
                    "background_order": 4,
                    "fit_range_GeV": [100.0, 160.0],
                    "weighting_scheme": "inverse_sqrt_bin_count",
                },
                "output_files_generated": [
                    "diphoton_mass_spectrum.json",
                    "diphoton_fit_summary.json",
                    "data_minus_background.json",
                    "interpretation.md",
                    "submission_trace.json",
                ],
                "reported_result": {
                    "signal_peak_position": 125.1,
                },
                "input_files_used": ["events.root"],
                "input_file_count": 1,
                "selected_events_total": 11,
                "cutflow_summary": {
                    "input_events": 42,
                    "selected_events": 11,
                },
            },
        },
    }


def sample_private_rubric() -> dict:
    return hyy_l1_private_rubric()


def canonical_hyy_task(**updates):
    task = load_task_spec(TASK_DIR)
    canonical = {
        "mode": "call_white",
        "needs_data": True,
        "requires_large_input_data": True,
        "supports_scenario_shared_input": True,
        "supports_local_shared_input": True,
        "input_strategy": "shared_manifest",
        "solver_response_mode": "submission_bundle_v1",
        "evaluation_mode": "directory_contract_and_private_rubric_v1",
    }
    canonical.update(updates)
    return task.model_copy(update=canonical)


@pytest.mark.parametrize("task_dir", [ZPEAK_TASK_DIR, TASK_DIR])
def test_public_tasks_use_bundle_directory_contract(task_dir):
    task = load_task_spec(task_dir)
    assert task.input_strategy == "download"
    assert task.solver_response_mode == "submission_bundle_v1"
    assert task.evaluation_mode == "directory_contract_and_private_rubric_v1"


def test_task_spec_capability_overrides_for_hyy_task():
    task = canonical_hyy_task()
    assert task.input_strategy == "shared_manifest"
    assert task.solver_response_mode == "submission_bundle_v1"
    assert task.evaluation_mode == "directory_contract_and_private_rubric_v1"


class DummyUpdater:
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


def make_secret_store_payload(task_spec) -> str:
    contract = load_submission_contract(task_spec)
    contract_hash = SecretStore("").contract_hash(contract)
    rubric_b64 = base64.b64encode(yaml.safe_dump(sample_private_rubric(), sort_keys=False).encode("utf-8")).decode("utf-8")
    return json.dumps(
        {
            "schema_version": 1,
            "tasks": {
                task_spec.id: {
                    "public_contract_sha256": contract_hash,
                    "private_rubric_yaml_b64": rubric_b64,
                }
            },
            "judge_env": {},
        }
    )


def make_secret_store_payload_with_wrong_hash(task_spec) -> str:
    rubric_b64 = base64.b64encode(yaml.safe_dump(sample_private_rubric(), sort_keys=False).encode("utf-8")).decode("utf-8")
    return json.dumps(
        {
            "schema_version": 1,
            "tasks": {
                task_spec.id: {
                    "public_contract_sha256": "deadbeef",
                    "private_rubric_yaml_b64": rubric_b64,
                }
            },
            "judge_env": {},
        }
    )


def test_resolve_input_access_requires_static_mount(tmp_path):
    task = canonical_hyy_task()
    cfg = GreenConfig(task_dirs=[str(TASK_DIR)])
    with pytest.raises(InputAccessError):
        resolve_input_access(task, cfg)


def test_resolve_input_access_allows_green_download_and_filters_non_root(tmp_path):
    task = canonical_hyy_task(max_files=2)
    shared_input = tmp_path / "2025e-13tev-beta" / "data" / "GamGam"
    shared_input.mkdir(parents=True)
    (shared_input / "events_a.root").write_text("placeholder", encoding="utf-8")
    (shared_input / "events_b.root").write_text("placeholder", encoding="utf-8")
    (shared_input / "green_download_manifest.json").write_text("{}", encoding="utf-8")
    cfg = GreenConfig(
        task_dirs=[str(TASK_DIR)],
        input_access_mode="local_shared_mount",
        shared_input_dir=str(tmp_path / "{release}" / "{dataset}" / "{skim}"),
        allow_green_download=True,
    )

    manifest = resolve_input_access(task, cfg)

    assert manifest is not None
    assert manifest["shared_input_dir"] == str(shared_input)
    assert manifest["input_manifest_path"] == str(shared_input / "input_manifest.json")
    assert [item["logical_name"] for item in manifest["files"]] == ["events_a.root", "events_b.root"]
    assert (shared_input / "input_manifest.json").exists()


def test_validate_task_capabilities_rejects_missing_contract_for_bundle_mode(tmp_path):
    task = canonical_hyy_task(submission_contract_path=None)
    cfg = GreenConfig(
        task_dirs=[str(TASK_DIR)],
        input_access_mode="local_shared_mount",
        shared_input_dir=str(tmp_path),
        input_manifest_path=str(tmp_path / "input_manifest.json"),
        allow_green_download=False,
    )
    engine = BenchmarkEngine()
    with pytest.raises(SubmissionBundleError):
        engine._validate_task_capabilities(task, cfg)


def test_apply_task_runtime_override_updates_allowed_fields():
    task = canonical_hyy_task()
    cfg = GreenConfig(
        task_dirs=[str(TASK_DIR)],
        task_overrides={
            task.id: {
                "mode": "mock",
                "input_strategy": "download",
                "max_files": 1,
                "release": "2026-test-release",
            }
        },
    )

    engine = BenchmarkEngine()
    effective, applied = engine._apply_task_runtime_override(task, cfg)

    assert effective is not None
    assert effective.mode == "mock"
    assert effective.input_strategy == "download"
    assert effective.max_files == 1
    assert effective.release == "2026-test-release"
    assert applied == {
        "mode": "mock",
        "input_strategy": "download",
        "max_files": 1,
        "release": "2026-test-release",
    }


def test_secret_backed_judge_falls_back_to_process_judge_when_secret_env_missing(monkeypatch):
    fallback_judge = object()
    engine = EvaluationEngine(fallback_judge=fallback_judge)

    task = canonical_hyy_task()
    monkeypatch.setenv("GREEN_SECRETS_JSON", make_secret_store_payload(task))
    secret_store = SecretStore()

    assert engine._build_secret_backed_judge(secret_store) is fallback_judge


def test_secret_backed_judge_falls_back_to_process_judge_when_secret_env_invalid(monkeypatch):
    fallback_judge = object()
    engine = EvaluationEngine(
        fallback_judge=fallback_judge,
        judge_factory=lambda: (_ for _ in ()).throw(RuntimeError("missing secret-backed key")),
    )

    task = canonical_hyy_task()
    payload = json.loads(make_secret_store_payload(task))
    payload["judge_env"] = {"HEPEX_JUDGE_PROVIDER": "openai"}
    secret_store = SecretStore(json.dumps(payload))

    assert engine._build_secret_backed_judge(secret_store) is fallback_judge


def test_parse_submission_bundle_rejects_large_payload():
    contract = load_submission_contract(canonical_hyy_task())
    bundle = sample_submission_bundle()
    bundle["artifacts"]["interpretation.md"] = "x" * (600 * 1024)
    with pytest.raises(SubmissionBundleError):
        parse_submission_bundle(bundle, contract)


def test_validate_submission_dir_hyy_v5_l1(tmp_path):
    task = canonical_hyy_task()
    bundle = sample_submission_bundle()
    for filename, payload in bundle["artifacts"].items():
        path = tmp_path / filename
        if filename.endswith(".md"):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
    report = validate_submission_dir(task, tmp_path)
    assert report["status"] == "ok"
    assert report["schema_errors"] == []
    assert report["missing_files"] == []


def test_private_rubric_loads_with_matching_contract_hash():
    task = canonical_hyy_task()
    secret_store = SecretStore(make_secret_store_payload(task))
    rubric = load_private_l1_rubric(task, secret_store)

    assert rubric["weights"]["execution"] == 0.35
    assert sorted(rubric["checks"].keys()) == [
        "analysis",
        "execution",
        "implementation",
        "pipeline",
        "reasoning",
        "validation",
    ]


def test_private_rubric_missing_on_contract_hash_mismatch():
    task = canonical_hyy_task()
    secret_store = SecretStore(make_secret_store_payload_with_wrong_hash(task))

    rubric = load_private_l1_rubric(task, secret_store)
    assert rubric == {}


@pytest.mark.asyncio
async def test_agent_hyy_v5_l1_submission_bundle_flow(monkeypatch, tmp_path):
    shared_input = tmp_path / "shared_input"
    shared_input.mkdir()
    (shared_input / "events.root").write_text("placeholder", encoding="utf-8")

    task = canonical_hyy_task()
    captured = {}

    async def fake_talk_to_agent(self, message, url, new_conversation=True, timeout=300):
        captured["message"] = json.loads(message)
        return json.dumps(sample_submission_bundle())

    monkeypatch.setattr("messenger.Messenger.talk_to_agent", fake_talk_to_agent)
    monkeypatch.setenv("GREEN_SECRETS_JSON", make_secret_store_payload(task))

    req = {
        "participants": {"purple_agent": "http://example.com"},
        "config": {
            "task_dirs": [str(TASK_DIR)],
            "data_dir": str(tmp_path / "runs"),
            "input_access_mode": "local_shared_mount",
            "shared_input_dir": str(shared_input),
            "input_manifest_path": str(shared_input / "input_manifest.json"),
            "allow_green_download": False,
        },
    }

    updater = DummyUpdater()
    agent = Agent()
    agent.benchmark_engine.task_loader = lambda _: task
    monkeypatch.setattr(agent.benchmark_engine.evaluation_engine, "_build_secret_backed_judge", lambda secret_store: None)
    await agent.run(new_agent_text_message(json.dumps(req)), updater)

    assert updater.rejected is None
    payload = captured["message"]
    assert "task_spec" not in payload
    assert payload["mode"] == task.mode
    assert payload["submission_contract"]["required_outputs"][0]["canonical_filename"] == "diphoton_mass_spectrum.json"
    assert payload["data"]["shared_input_dir"] == str(shared_input)
    assert payload["data"]["read_only_for_solver"] is True
    assert payload["data"]["max_files"] == task.max_files
    assert payload["data"]["work_dir"].endswith(f"/{task.id}/solver_work")
    assert payload["data"]["output_dir"] == payload["data"]["work_dir"]

    runs_root = Path(req["config"]["data_dir"]) / "runs"
    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    task_dir = run_dirs[0] / task.id
    assert (task_dir / "submission_bundle_raw.json").exists()
    assert (task_dir / "input_manifest.json").exists()
    assert (task_dir / "diphoton_fit_summary.json").exists()
    assert (shared_input / "input_manifest.json").exists()

    report = json.loads((task_dir / "judge_output.json").read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["hard_checks_passed"] is True
    assert report["final"]["total_score"] > 0.0
    assert sorted(report["dimension_scores"].keys()) == [
        "analysis",
        "execution",
        "implementation",
        "pipeline",
        "reasoning",
        "validation",
    ]
    assert report["final"]["normalized_score"] is not None


@pytest.mark.asyncio
async def test_agent_download_strategy_delegates_download_to_solver(monkeypatch, tmp_path):
    task = canonical_hyy_task(input_strategy="download", mode="call_white")
    captured = {}

    async def fake_talk_to_agent(self, message, url, new_conversation=True, timeout=300):
        captured["message"] = json.loads(message)
        return json.dumps(sample_submission_bundle())

    monkeypatch.setattr("messenger.Messenger.talk_to_agent", fake_talk_to_agent)
    monkeypatch.setenv("GREEN_SECRETS_JSON", make_secret_store_payload(task))

    req = {
        "participants": {"purple_agent": "http://example.com"},
        "config": {
            "task_dirs": [str(TASK_DIR)],
            "data_dir": str(tmp_path / "runs"),
        },
    }

    updater = DummyUpdater()
    agent = Agent()
    agent.benchmark_engine.task_loader = lambda _: task
    monkeypatch.setattr(agent.benchmark_engine.evaluation_engine, "_build_secret_backed_judge", lambda secret_store: None)
    await agent.run(new_agent_text_message(json.dumps(req)), updater)

    assert updater.rejected is None
    payload = captured["message"]
    assert payload["data"]["release"] == task.release
    assert payload["data"]["dataset"] == task.dataset
    assert payload["data"]["skim"] == task.skim
    assert payload["data"]["max_files"] == task.max_files
    assert payload["data"]["input_strategy"] == "download"
    assert payload["data"]["work_dir"].endswith(f"/{task.id}/solver_work")
    assert payload["data"]["output_dir"] == payload["data"]["work_dir"]

    runs_root = Path(req["config"]["data_dir"]) / "runs"
    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    task_dir = run_dirs[0] / task.id
    data_info = json.loads((task_dir / "data_info.json").read_text(encoding="utf-8"))
    assert data_info["download_managed_by"] == "solver"


@pytest.mark.asyncio
async def test_agent_hyy_v5_l1_mock_mode_scores_from_private_rubric(monkeypatch, tmp_path):
    shared_input = tmp_path / "shared_input"
    shared_input.mkdir()
    (shared_input / "events.root").write_text("placeholder", encoding="utf-8")

    task = canonical_hyy_task(mode="mock")
    monkeypatch.setenv("GREEN_SECRETS_JSON", make_secret_store_payload(task))

    req = {
        "participants": {"purple_agent": "http://unused.example.com"},
        "config": {
            "task_dirs": [str(TASK_DIR)],
            "data_dir": str(tmp_path / "runs"),
            "input_access_mode": "local_shared_mount",
            "shared_input_dir": str(shared_input),
            "input_manifest_path": str(shared_input / "input_manifest.json"),
            "allow_green_download": False,
        },
    }

    updater = DummyUpdater()
    agent = Agent()
    agent.benchmark_engine.task_loader = lambda _: task
    monkeypatch.setattr(agent.benchmark_engine.evaluation_engine, "_build_secret_backed_judge", lambda secret_store: None)
    await agent.run(new_agent_text_message(json.dumps(req)), updater)

    assert updater.rejected is None

    runs_root = Path(req["config"]["data_dir"]) / "runs"
    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    task_dir = run_dirs[0] / task.id

    report = json.loads((task_dir / "judge_output.json").read_text(encoding="utf-8"))
    assert report["status"] == "ok"
    assert report["hard_checks_passed"] is True
    assert report["dimension_scores"] == {
        "execution": 1.0,
        "pipeline": 1.0,
        "implementation": 1.0,
        "reasoning": 0.0,
        "analysis": 1.0,
        "validation": 0.0,
    }
    assert report["check_results"]
    assert report["final"]["total_score"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_agent_hyy_v5_l1_mock_mode_can_run_without_shared_mount(monkeypatch, tmp_path):
    task = canonical_hyy_task(mode="mock")
    monkeypatch.setenv("GREEN_SECRETS_JSON", make_secret_store_payload(task))

    req = {
        "participants": {"purple_agent": "http://unused.example.com"},
        "config": {
            "task_dirs": [str(TASK_DIR)],
            "data_dir": str(tmp_path / "runs"),
        },
    }

    updater = DummyUpdater()
    agent = Agent()
    agent.benchmark_engine.task_loader = lambda _: task
    monkeypatch.setattr(agent.benchmark_engine.evaluation_engine, "_build_secret_backed_judge", lambda secret_store: None)
    await agent.run(new_agent_text_message(json.dumps(req)), updater)

    assert updater.rejected is None

    runs_root = Path(req["config"]["data_dir"]) / "runs"
    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    task_dir = run_dirs[0] / task.id

    report = json.loads((task_dir / "judge_output.json").read_text(encoding="utf-8"))
    data_info = json.loads((task_dir / "data_info.json").read_text(encoding="utf-8"))
    manifest = json.loads((task_dir / "mock_shared_input" / "input_manifest.json").read_text(encoding="utf-8"))

    assert report["status"] == "ok"
    assert report["final"]["normalized_score"] == pytest.approx(0.9)
    assert data_info["n_files"] == 1
    assert manifest["synthetic_for_mock_mode"] is True
    assert manifest["files"][0]["logical_name"] == "events.root"


@pytest.mark.asyncio
async def test_agent_skips_task_when_override_disables_it(monkeypatch, tmp_path):
    task = canonical_hyy_task()
    req = {
        "participants": {},
        "config": {
            "task_dirs": [str(TASK_DIR)],
            "data_dir": str(tmp_path / "runs"),
            "task_overrides": {
                task.id: {
                    "enabled": False,
                    "mode": "mock",
                }
            },
        },
    }

    updater = DummyUpdater()
    agent = Agent()
    agent.benchmark_engine.task_loader = lambda _: task
    await agent.run(new_agent_text_message(json.dumps(req)), updater)

    runs_root = Path(req["config"]["data_dir"]) / "runs"
    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    assert not (run_dirs[0] / task.id).exists()

    summary_artifacts = [artifact for artifact in updater.artifacts if artifact[0] == "Summary"]
    assert len(summary_artifacts) == 1
    assert len(summary_artifacts[0][1]) == 1
    assert "Done." in summary_artifacts[0][1][0].root.text

    summary_payload = json.loads((run_dirs[0] / "run_summary.json").read_text(encoding="utf-8"))
    assert summary_payload["tasks"] == []
    assert summary_payload["score_total"] == 0.0
    assert summary_payload["score_max"] == 0.0


@pytest.mark.asyncio
async def test_agent_hyy_v5_l1_reports_public_score_when_hidden_rubric_unavailable(monkeypatch, tmp_path):
    shared_input = tmp_path / "shared_input"
    shared_input.mkdir()
    (shared_input / "events.root").write_text("placeholder", encoding="utf-8")

    task = canonical_hyy_task()

    async def fake_talk_to_agent(self, message, url, new_conversation=True, timeout=300):
        return json.dumps(sample_submission_bundle())

    monkeypatch.setattr("messenger.Messenger.talk_to_agent", fake_talk_to_agent)
    monkeypatch.setenv("GREEN_SECRETS_JSON", make_secret_store_payload_with_wrong_hash(task))

    req = {
        "participants": {"purple_agent": "http://example.com"},
        "config": {
            "task_dirs": [str(TASK_DIR)],
            "data_dir": str(tmp_path / "runs"),
            "input_access_mode": "local_shared_mount",
            "shared_input_dir": str(shared_input),
            "input_manifest_path": str(shared_input / "input_manifest.json"),
            "allow_green_download": False,
        },
    }

    updater = DummyUpdater()
    agent = Agent()
    agent.benchmark_engine.task_loader = lambda _: task
    await agent.run(new_agent_text_message(json.dumps(req)), updater)

    runs_root = Path(req["config"]["data_dir"]) / "runs"
    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    task_dir = run_dirs[0] / task.id

    report = json.loads((task_dir / "judge_output.json").read_text(encoding="utf-8"))
    assert report["status"] == "public_ok_hidden_unavailable"
    assert report["hard_checks_passed"] is True
    assert report["public_scores"]["contract_pass"] == 1.0
    assert report["hidden_scores"]["status"] == "unavailable"
    assert report["final"]["normalized_score"] == 1.0
    assert report["dimension_scores"] == {
        "execution": None,
        "pipeline": None,
        "implementation": None,
        "reasoning": None,
        "analysis": None,
        "validation": None,
    }
    assert any(issue["code"] == "PRIVATE_RUBRIC_UNAVAILABLE" for issue in report["issues"])


@pytest.mark.asyncio
async def test_hyy_v5_l1_green_report_is_leaderboard_ready(monkeypatch, tmp_path):
    shared_input = tmp_path / "shared_input"
    shared_input.mkdir()
    (shared_input / "events.root").write_text("placeholder", encoding="utf-8")

    task = canonical_hyy_task(mode="mock")
    monkeypatch.setenv("GREEN_SECRETS_JSON", make_secret_store_payload(task))

    req = {
        "participants": {"purple_agent": "http://unused.example.com"},
        "config": {
            "task_dirs": [str(TASK_DIR)],
            "data_dir": str(tmp_path / "runs"),
            "input_access_mode": "local_shared_mount",
            "shared_input_dir": str(shared_input),
            "input_manifest_path": str(shared_input / "input_manifest.json"),
            "allow_green_download": False,
        },
    }

    updater = DummyUpdater()
    agent = Agent()
    agent.benchmark_engine.task_loader = lambda _: task
    monkeypatch.setattr(agent.benchmark_engine.evaluation_engine, "_build_secret_backed_judge", lambda secret_store: None)
    await agent.run(new_agent_text_message(json.dumps(req)), updater)

    runs_root = Path(req["config"]["data_dir"]) / "runs"
    run_dirs = [path for path in runs_root.iterdir() if path.is_dir()]
    assert len(run_dirs) == 1
    task_dir = run_dirs[0] / task.id
    report = json.loads((task_dir / "judge_output.json").read_text(encoding="utf-8"))

    for key in ["task_id", "type", "status", "hard_checks_passed", "dimension_scores", "check_results", "final"]:
        assert key in report
    for key in ["total_score", "max_score", "normalized_score"]:
        assert key in report["final"]
    assert sorted(report["dimension_scores"].keys()) == [
        "analysis",
        "execution",
        "implementation",
        "pipeline",
        "reasoning",
        "validation",
    ]


@pytest.mark.asyncio
async def test_agent_routes_by_capability_not_task_id(monkeypatch, tmp_path):
    shared_input = tmp_path / "shared_input"
    shared_input.mkdir()
    (shared_input / "events.root").write_text("placeholder", encoding="utf-8")

    task = canonical_hyy_task(id="t999_custom_l1")
    captured = {"prepare": 0, "bundle": 0, "eval": 0}

    async def fake_prepare(self, task, cfg, task_eval_dir, observer):
        captured["prepare"] += 1
        return (
            {
                "shared_input_dir": str(shared_input),
                "input_manifest_path": str(shared_input / "input_manifest.json"),
                "n_files": 1,
            },
            {
                "shared_input_dir": str(shared_input),
                "input_manifest_path": str(shared_input / "input_manifest.json"),
                "files": [{"logical_name": "events.root", "path": str(shared_input / "events.root"), "size_bytes": 11}],
            },
        )

    async def fake_bundle(self, task, task_eval_dir, input_manifest, persist_payloads, solver_transport, solver_backend):
        captured["bundle"] += 1
        assert solver_backend == "agent_1_oh"
        submission_trace = sample_submission_bundle()["artifacts"]["submission_trace.json"]
        (task_eval_dir / "submission_trace.json").write_text(json.dumps(submission_trace), encoding="utf-8")
        return {"submission_trace": submission_trace}

    def fake_evaluate(self, task, task_eval_dir):
        captured["eval"] += 1
        return {
            "task_id": task.id,
            "type": task.type,
            "status": "ok",
            "hard_checks_passed": True,
            "final": {"total_score": 1.0, "max_score": 1.0, "normalized_score": 1.0},
        }

    monkeypatch.setattr(BenchmarkEngine, "_prepare_task_input", fake_prepare)
    monkeypatch.setattr(BenchmarkEngine, "_collect_solver_output", fake_bundle)
    monkeypatch.setattr(EvaluationEngine, "evaluate_submission", fake_evaluate)

    req = {
        "participants": {"purple_agent": "http://example.com"},
        "config": {
            "task_dirs": [str(TASK_DIR)],
            "data_dir": str(tmp_path / "runs"),
            "input_access_mode": "local_shared_mount",
            "shared_input_dir": str(shared_input),
            "input_manifest_path": str(shared_input / "input_manifest.json"),
            "allow_green_download": False,
        },
    }

    updater = DummyUpdater()
    agent = Agent()
    agent.benchmark_engine.task_loader = lambda _: task
    await agent.run(new_agent_text_message(json.dumps(req)), updater)

    assert updater.rejected is None
    assert captured == {"prepare": 1, "bundle": 1, "eval": 1}


@pytest.mark.asyncio
async def test_green_managed_download_populates_shared_manifest(monkeypatch, tmp_path):
    task = canonical_hyy_task(max_files=2)
    shared_input = tmp_path / "shared_input" / "2025e-13tev-beta" / "data" / "GamGam"
    task_eval_dir = tmp_path / "task_eval"
    cfg = GreenConfig(
        task_dirs=[str(TASK_DIR)],
        input_access_mode="local_shared_mount",
        shared_input_dir=str(tmp_path / "shared_input" / "{release}" / "{dataset}" / "{skim}"),
        allow_green_download=True,
    )

    def fake_ensure_downloaded(**kwargs):
        assert kwargs["skim"] == "GamGam"
        assert kwargs["max_files"] == 2
        output_dir = Path(kwargs["output_dir"])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "events_a.root").write_text("placeholder", encoding="utf-8")
        (output_dir / "events_b.root").write_text("placeholder", encoding="utf-8")
        (output_dir / "notes.txt").write_text("not input", encoding="utf-8")
        return {
            "release": kwargs["release"],
            "dataset": kwargs["dataset"],
            "skim": kwargs["skim"],
            "protocol": kwargs["protocol"],
            "output_dir": str(output_dir),
            "n_requested": 2,
            "n_ok": 2,
            "n_fail": 0,
            "local_paths": [str(output_dir / "events_a.root"), str(output_dir / "events_b.root")],
            "results": [],
            "raw_urls": [],
        }

    class Observer:
        def __init__(self):
            self.statuses = []

        async def status(self, text):
            self.statuses.append(text)

    monkeypatch.setattr("engine.benchmark_engine.ensure_atlas_open_data_downloaded", fake_ensure_downloaded)

    observer = Observer()
    engine = BenchmarkEngine()
    data_info, manifest = await engine._prepare_task_input(task, cfg, task_eval_dir, observer)

    assert data_info is not None
    assert manifest is not None
    assert data_info["download_managed_by"] == "green"
    assert data_info["download_summary"]["n_ok"] == 2
    assert data_info["n_files"] == 2
    assert data_info["shared_input_dir"] == str(shared_input)
    assert data_info["input_manifest_path"] == str(shared_input / "input_manifest.json")
    assert [item["logical_name"] for item in manifest["files"]] == ["events_a.root", "events_b.root"]
    assert (shared_input / "input_manifest.json").exists()
    assert (shared_input / "green_download_manifest.json").exists()
    assert (task_eval_dir / "green_download_manifest.json").exists()
    assert any("Green downloading shared input" in status for status in observer.statuses)


@pytest.mark.asyncio
async def test_agent_solver_transport_uses_configured_timeout():
    captured = {}

    class Messenger:
        async def talk_to_agent(self, **kwargs):
            captured.update(kwargs)
            return "{}"

    request = EvalRequest.model_validate(
        {
            "participants": {"purple_agent": "http://example.com"},
            "config": {"solver_request_timeout_seconds": 1800},
        }
    )
    transport = AgentSolverTransport(messenger=Messenger(), request=request)

    await transport.request_submission_bundle({"status": "test"})

    assert captured["timeout"] == 1800
    assert captured["new_conversation"] is True
