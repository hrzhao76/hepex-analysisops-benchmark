import json
from pathlib import Path

import pytest

from engine.contract_validator import validate_submission_dir
from engine.submission_bundle import (
    SubmissionBundleError,
    materialize_submission_bundle,
    parse_submission_bundle,
)
from tasks.task_spec import load_task_spec
from utils.mock_traces import get_mock_bundle


ROOT = Path(__file__).parent.parent
ZPEAK_DIR = ROOT / "tasks_public" / "t001_zpeak_fit"


def materialize_bundle(task_dir: Path, output_dir: Path) -> None:
    task = load_task_spec(task_dir)
    bundle = get_mock_bundle(task.type, task.id)
    for filename, payload in bundle["artifacts"].items():
        path = output_dir / filename
        if filename.endswith(".md"):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")


def test_validate_submission_dir_accepts_public_bundle(tmp_path):
    task = load_task_spec(ZPEAK_DIR)
    materialize_bundle(ZPEAK_DIR, tmp_path)

    report = validate_submission_dir(task, tmp_path)

    assert report["status"] == "ok"
    assert report["hard_checks_passed"] is True
    assert report["missing_files"] == []
    assert report["schema_errors"] == []
    assert report["final"]["normalized_score"] == 1.0


def test_validate_submission_dir_reports_missing_required_file(tmp_path):
    task = load_task_spec(ZPEAK_DIR)
    materialize_bundle(ZPEAK_DIR, tmp_path)
    (tmp_path / "fit_summary.json").unlink()

    report = validate_submission_dir(task, tmp_path)

    assert report["status"] == "contract_fail"
    assert report["hard_checks_passed"] is False
    assert report["missing_files"] == ["fit_summary.json"]


def test_validate_submission_dir_reports_json_schema_error(tmp_path):
    task = load_task_spec(ZPEAK_DIR)
    materialize_bundle(ZPEAK_DIR, tmp_path)
    bad_summary = json.loads((tmp_path / "fit_summary.json").read_text(encoding="utf-8"))
    bad_summary["fit_result"].pop("sigma")
    (tmp_path / "fit_summary.json").write_text(json.dumps(bad_summary), encoding="utf-8")

    report = validate_submission_dir(task, tmp_path)

    assert report["status"] == "contract_fail"
    assert any("fit_result.sigma" in err for err in report["schema_errors"])


def test_validate_submission_dir_reports_markdown_error(tmp_path):
    task = load_task_spec(ZPEAK_DIR)
    materialize_bundle(ZPEAK_DIR, tmp_path)
    (tmp_path / "interpretation.md").write_text("", encoding="utf-8")

    report = validate_submission_dir(task, tmp_path)

    assert report["status"] == "contract_fail"
    assert any("interpretation.md" in err for err in report["schema_errors"])


def test_submission_bundle_allows_declared_optional_image_ref(tmp_path):
    contract = {
        "required_outputs": [
            {"name": "summary", "canonical_filename": "summary.json", "type": "json"},
        ],
        "optional_outputs": [
            {"name": "plot", "canonical_filename": "plot_ref.json", "type": "image_ref"},
        ],
        "schemas": {
            "summary.json": {"required_fields": ["status"]},
            "plot_ref.json": {"required_fields": ["path", "description"]},
        },
    }
    bundle = {
        "status": "ok",
        "artifacts": {
            "summary.json": {"status": "ok"},
            "plot_ref.json": {"path": "plots/fit.png", "description": "Fit plot"},
        },
    }

    parsed = parse_submission_bundle(bundle, contract)
    manifest = materialize_submission_bundle(parsed, contract, tmp_path)

    assert (tmp_path / "summary.json").exists()
    assert (tmp_path / "plot_ref.json").exists()
    assert [entry["canonical_filename"] for entry in manifest["artifacts"]] == ["summary.json", "plot_ref.json"]


def test_submission_bundle_rejects_undeclared_artifact():
    contract = {
        "required_outputs": [
            {"name": "summary", "canonical_filename": "summary.json", "type": "json"},
        ],
        "optional_outputs": [],
        "schemas": {"summary.json": {"required_fields": ["status"]}},
    }
    bundle = {
        "artifacts": {
            "summary.json": {"status": "ok"},
            "extra.json": {},
        }
    }

    with pytest.raises(SubmissionBundleError, match="unexpected artifact"):
        parse_submission_bundle(bundle, contract)
