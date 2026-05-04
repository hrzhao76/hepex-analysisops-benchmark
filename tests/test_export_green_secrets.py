import base64
import gzip
import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path

import yaml


ROOT = Path(__file__).parent.parent
SCRIPT_PATH = ROOT / "scripts" / "export_green_secrets.py"


def load_export_script():
    spec = importlib.util.spec_from_file_location("export_green_secrets", SCRIPT_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_task_package(base: Path, task_id: str) -> Path:
    task_dir = base / task_id
    task_dir.mkdir()
    (task_dir / "task_spec.yaml").write_text(
        yaml.safe_dump(
            {
                "id": task_id,
                "type": "unit_test",
                "mode": "call_white",
                "needs_data": False,
                "submission_contract_path": "submission_contract.yaml",
                "solver_response_mode": "submission_bundle_v1",
                "evaluation_mode": "directory_contract_and_private_rubric_v1",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (task_dir / "submission_contract.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 2,
                "task_id": task_id,
                "required_outputs": [
                    {
                        "name": "submission_trace",
                        "canonical_filename": "submission_trace.json",
                        "type": "json",
                    }
                ],
                "schemas": {
                    "submission_trace.json": {
                        "required_fields": ["workflow_stages"],
                        "field_types": {"workflow_stages": "array_object"},
                    }
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return task_dir


def write_private_rubric(path: Path) -> Path:
    path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "weights": {"execution": 1.0},
                "checks": {
                    "execution": [
                        {
                            "id": "required_trace",
                            "type": "structural",
                            "condition": {"required_files": ["submission_trace.json"]},
                            "score": 1.0,
                        }
                    ]
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_build_green_secrets_json_includes_multiple_tasks(tmp_path):
    script = load_export_script()
    task_a = write_task_package(tmp_path, "task_a")
    task_b = write_task_package(tmp_path, "task_b")
    rubric_a = write_private_rubric(tmp_path / "rubric_a.yaml")
    rubric_b = write_private_rubric(tmp_path / "rubric_b.yaml")

    secret_json, summaries = script.build_green_secrets_json(
        sources=[
            script.TaskSecretSource(task_dir=task_a, private_rubric_path=rubric_a),
            script.TaskSecretSource(task_dir=task_b, private_rubric_path=rubric_b),
        ],
        judge_env=[("HEPEX_OPENAI_MODEL", "unit-test-model")],
    )

    payload = json.loads(secret_json)
    assert sorted(payload["tasks"]) == ["task_a", "task_b"]
    assert payload["judge_env"] == {"HEPEX_OPENAI_MODEL": "unit-test-model"}
    assert [task_id for task_id, _hash in summaries] == ["task_a", "task_b"]

    decoded = gzip.decompress(
        base64.b64decode(payload["tasks"]["task_a"]["private_rubric_yaml_gz_b64"])
    ).decode("utf-8")
    assert yaml.safe_load(decoded)["checks"]["execution"][0]["id"] == "required_trace"


def test_build_green_secrets_json_can_emit_legacy_plain_encoding(tmp_path):
    script = load_export_script()
    task_a = write_task_package(tmp_path, "task_a")
    rubric_a = write_private_rubric(tmp_path / "rubric_a.yaml")

    secret_json, _summaries = script.build_green_secrets_json(
        sources=[script.TaskSecretSource(task_dir=task_a, private_rubric_path=rubric_a)],
        judge_env=[],
        encoding="plain",
    )

    entry = json.loads(secret_json)["tasks"]["task_a"]
    assert "private_rubric_yaml_b64" in entry
    assert "private_rubric_yaml_gz_b64" not in entry


def test_requested_sources_defaults_to_hyy_l1_l2_l3_and_hzz_l1_l2_l3():
    script = load_export_script()

    sources = script.requested_sources(Namespace(task_dir=None, private_rubric=None, suite="all"))

    assert [source.task_dir.name for source in sources] == [
        "t002_hyy_v5_l1",
        "t003_hyy_v5_l2",
        "t004_hyy_v5_l3",
        "t005_hzz4l_l1",
        "t006_hzz4l_l2",
        "t007_hzz4l_l3",
    ]


def test_requested_sources_can_export_hyy_suite_only():
    script = load_export_script()

    sources = script.requested_sources(Namespace(task_dir=None, private_rubric=None, suite="hyy"))

    assert [source.task_dir.name for source in sources] == [
        "t002_hyy_v5_l1",
        "t003_hyy_v5_l2",
        "t004_hyy_v5_l3",
    ]


def test_requested_sources_can_export_hzz_suite_only():
    script = load_export_script()

    sources = script.requested_sources(Namespace(task_dir=None, private_rubric=None, suite="hzz"))

    assert [source.task_dir.name for source in sources] == [
        "t005_hzz4l_l1",
        "t006_hzz4l_l2",
        "t007_hzz4l_l3",
    ]


def test_requested_sources_infers_l2_private_rubric_for_l2_single_task():
    script = load_export_script()

    sources = script.requested_sources(
        Namespace(task_dir=script.DEFAULT_L2_TASK_DIR, private_rubric=None, suite="all")
    )

    assert len(sources) == 1
    assert sources[0].task_dir.name == "t003_hyy_v5_l2"
    assert sources[0].private_rubric_path.name == "hyy_v5_l2_private_rubric.yaml"


def test_requested_sources_infers_l3_private_rubric_for_l3_single_task():
    script = load_export_script()

    sources = script.requested_sources(
        Namespace(task_dir=script.DEFAULT_L3_TASK_DIR, private_rubric=None, suite="all")
    )

    assert len(sources) == 1
    assert sources[0].task_dir.name == "t004_hyy_v5_l3"
    assert sources[0].private_rubric_path.name == "hyy_v5_l3_private_rubric.yaml"


def test_requested_sources_infers_hzz_l1_private_rubric_for_hzz_single_task():
    script = load_export_script()

    sources = script.requested_sources(
        Namespace(task_dir=script.DEFAULT_HZZ_L1_TASK_DIR, private_rubric=None, suite="all")
    )

    assert len(sources) == 1
    assert sources[0].task_dir.name == "t005_hzz4l_l1"
    assert sources[0].private_rubric_path.name == "hzz4l_l1_private_rubric.yaml"


def test_requested_sources_infers_hzz_l2_private_rubric_for_hzz_single_task():
    script = load_export_script()

    sources = script.requested_sources(
        Namespace(task_dir=script.DEFAULT_HZZ_L2_TASK_DIR, private_rubric=None, suite="all")
    )

    assert len(sources) == 1
    assert sources[0].task_dir.name == "t006_hzz4l_l2"
    assert sources[0].private_rubric_path.name == "hzz4l_l2_private_rubric.yaml"


def test_requested_sources_infers_hzz_l3_private_rubric_for_hzz_single_task():
    script = load_export_script()

    sources = script.requested_sources(
        Namespace(task_dir=script.DEFAULT_HZZ_L3_TASK_DIR, private_rubric=None, suite="all")
    )

    assert len(sources) == 1
    assert sources[0].task_dir.name == "t007_hzz4l_l3"
    assert sources[0].private_rubric_path.name == "hzz4l_l3_private_rubric.yaml"


def test_resolve_private_rubric_keeps_existing_cache_when_fallback_changes(tmp_path):
    script = load_export_script()
    cached = tmp_path / "cached.yaml"
    fallback = tmp_path / "fallback.yaml"
    cached.write_text("version: 1\nsource: cached\n", encoding="utf-8")
    fallback.write_text("version: 1\nsource: fallback\n", encoding="utf-8")

    resolved = script.resolve_private_rubric_path(
        script.TaskSecretSource(
            task_dir=tmp_path,
            private_rubric_path=cached,
            fallback_private_rubric_path=fallback,
        )
    )

    assert resolved == cached
    assert cached.read_text(encoding="utf-8") == "version: 1\nsource: cached\n"


def test_resolve_private_rubric_seeds_missing_cache_from_fallback(tmp_path):
    script = load_export_script()
    cached = tmp_path / "cached.yaml"
    fallback = tmp_path / "fallback.yaml"
    fallback.write_text("version: 1\nsource: fallback\n", encoding="utf-8")

    resolved = script.resolve_private_rubric_path(
        script.TaskSecretSource(
            task_dir=tmp_path,
            private_rubric_path=cached,
            fallback_private_rubric_path=fallback,
        )
    )

    assert resolved == cached
    assert cached.read_text(encoding="utf-8") == "version: 1\nsource: fallback\n"
