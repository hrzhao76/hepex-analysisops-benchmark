import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from engine.evaluation import EvaluationEngine
from engine.llm_judge import LLMJudgeResult
from engine.package_loader import load_submission_contract
from engine.secret_store import SecretStore
from tasks.task_spec import load_task_spec
from utils.mock_private_rubrics import hyy_l1_private_rubric
from utils.mock_traces import get_mock_bundle


ROOT = Path(__file__).parent.parent
HYY_TASK_DIR = ROOT / "tasks_public" / "t002_hyy_v5_l1"


def materialize_bundle(bundle: dict, output_dir: Path) -> None:
    for filename, payload in bundle["artifacts"].items():
        path = output_dir / filename
        if filename.endswith(".md"):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")


def secret_payload(task, *, matching_hash: bool = True) -> str:
    contract = load_submission_contract(task)
    contract_hash = SecretStore("").contract_hash(contract) if matching_hash else "deadbeef"
    rubric_b64 = base64.b64encode(
        yaml.safe_dump(hyy_l1_private_rubric(), sort_keys=False).encode("utf-8")
    ).decode("utf-8")
    return json.dumps(
        {
            "schema_version": 1,
            "tasks": {
                task.id: {
                    "public_contract_sha256": contract_hash,
                    "private_rubric_yaml_b64": rubric_b64,
                }
            },
            "judge_env": {},
        }
    )


def test_evaluation_engine_returns_contract_fail_for_missing_artifacts(tmp_path):
    task = load_task_spec(HYY_TASK_DIR)
    report = EvaluationEngine().evaluate_submission(task, tmp_path)

    assert report["status"] == "contract_fail"
    assert report["hard_checks_passed"] is False
    assert report["missing_files"]


def test_evaluation_engine_returns_public_only_when_private_rubric_missing(tmp_path):
    task = load_task_spec(HYY_TASK_DIR)
    materialize_bundle(get_mock_bundle(task.type, task.id), tmp_path)

    engine = EvaluationEngine(secret_store_factory=lambda: SecretStore(secret_payload(task, matching_hash=False)))
    report = engine.evaluate_submission(task, tmp_path)

    assert report["status"] == "public_ok_hidden_unavailable"
    assert report["score_visibility"] == "public_only"
    assert report["public_scores"]["contract_pass"] == 1.0
    assert report["hidden_scores"]["status"] == "unavailable"
    assert report["final"]["normalized_score"] == 1.0


def test_evaluation_engine_returns_hidden_score_with_private_rubric(tmp_path):
    task = load_task_spec(HYY_TASK_DIR)
    materialize_bundle(get_mock_bundle(task.type, task.id), tmp_path)

    engine = EvaluationEngine(secret_store_factory=lambda: SecretStore(secret_payload(task)))
    report = engine.evaluate_submission(task, tmp_path)

    assert report["status"] == "ok"
    assert report["score_visibility"] == "official_with_hidden"
    assert report["hidden_scores"]["status"] == "ok"
    assert report["final"]["normalized_score"] == pytest.approx(0.9)


def test_evaluation_engine_preserves_interpretation_text_for_llm_judge(tmp_path):
    class RecordingJudge:
        def judge(self, spec, trace, rule_signals, rule_issues):
            evidence = trace["evidence"]
            assert isinstance(evidence["interpretation"], str)
            assert "Higgs-like excess" in evidence["interpretation"]
            return LLMJudgeResult(
                ok=True,
                raw_text='{"pass": true}',
                parsed={"pass": True, "explanation": "ok", "notes": []},
                error="",
            )

    task = load_task_spec(HYY_TASK_DIR)
    materialize_bundle(get_mock_bundle(task.type, task.id), tmp_path)

    engine = EvaluationEngine(
        fallback_judge=RecordingJudge(),
        secret_store_factory=lambda: SecretStore(secret_payload(task)),
    )
    report = engine.evaluate_submission(task, tmp_path)

    reasoning = [check for check in report["check_results"] if check["id"] == "interpretation_logically_consistent"][0]
    assert reasoning["passed"] is True
    assert report["final"]["normalized_score"] == pytest.approx(1.0)


def test_evaluation_engine_rejects_unsupported_mode(tmp_path):
    task = SimpleNamespace(id="bad", type="bad", evaluation_mode="unsupported")

    with pytest.raises(RuntimeError, match="Unsupported evaluation_mode"):
        EvaluationEngine().evaluate_submission(task, tmp_path)


def test_evaluation_engine_secret_judge_falls_back_when_factory_fails():
    fallback_judge = object()
    payload = {
        "schema_version": 1,
        "tasks": {},
        "judge_env": {"HEPEX_JUDGE_PROVIDER": "openai"},
    }
    engine = EvaluationEngine(
        fallback_judge=fallback_judge,
        judge_factory=lambda: (_ for _ in ()).throw(RuntimeError("missing secret-backed key")),
    )

    assert engine._build_secret_backed_judge(SecretStore(json.dumps(payload))) is fallback_judge
