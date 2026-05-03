from pathlib import Path

import yaml

from engine.schema_validator import (
    validate_private_rubric_document,
    validate_submission_contract_document,
    validate_task_package_dir,
    validate_task_package_manifest_document,
    validate_task_spec_document,
)
from utils.mock_private_rubrics import hyy_l1_private_rubric


ROOT = Path(__file__).parent.parent
TASKS_PUBLIC = ROOT / "tasks_public"


def public_task_dirs() -> list[Path]:
    return sorted(path for path in TASKS_PUBLIC.iterdir() if (path / "task_spec.yaml").exists())


def test_public_tasks_validate_against_public_schemas():
    for task_dir in public_task_dirs():
        task_spec = yaml.safe_load((task_dir / "task_spec.yaml").read_text(encoding="utf-8")) or {}
        contract = yaml.safe_load((task_dir / "submission_contract.yaml").read_text(encoding="utf-8")) or {}

        assert validate_task_spec_document(task_spec) == []
        assert validate_submission_contract_document(contract) == []
        assert validate_task_package_dir(task_dir, require_manifest=True) == []


def test_private_rubric_schema_accepts_hyy_l1_rubric():
    assert validate_private_rubric_document(hyy_l1_private_rubric()) == []


def test_manifest_schema_detects_hash_mismatch(tmp_path):
    (tmp_path / "task_spec.yaml").write_text("id: demo\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "package_id": "demo",
        "task_id": "demo",
        "source": "manual",
        "status": "published",
        "schema_versions": {"task_spec": 1},
        "files": {
            "public": [{"path": "task_spec.yaml", "sha256": "deadbeef"}],
            "private": [],
        },
    }

    issues = validate_task_package_manifest_document(manifest, package_dir=tmp_path)

    assert any("sha256 mismatch" in issue for issue in issues)
