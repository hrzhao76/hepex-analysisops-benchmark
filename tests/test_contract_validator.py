import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

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
HZZ_L3_DIR = ROOT / "tasks_public" / "t007_hzz4l_l3"


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


def test_submission_bundle_rejects_top_level_error_status():
    contract = {
        "required_outputs": [
            {"name": "summary", "canonical_filename": "summary.json", "type": "json"},
        ],
        "optional_outputs": [],
        "schemas": {"summary.json": {"required_fields": ["status"]}},
    }
    bundle = {"status": "error", "error": "analysis failed before histogramming"}

    with pytest.raises(SubmissionBundleError, match="analysis failed"):
        parse_submission_bundle(bundle, contract)


def test_contract_validator_requires_structured_scientific_decisions(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {
                "required_fields": ["scientific_decisions"],
                "field_types": {"scientific_decisions": "array_object"},
                "nested_required_fields": {
                    "scientific_decisions": {
                        "required_fields": ["decision", "reason", "impact_on_analysis"]
                    }
                },
            }
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    (submission_dir / "submission_trace.json").write_text(
        json.dumps({"scientific_decisions": [{"decision": "use a counting window", "reason": "localized excess"}]}),
        encoding="utf-8",
    )
    task = SimpleNamespace(
        id="structured_trace",
        type="generic_l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = validate_submission_dir(task, submission_dir)

    assert report["status"] == "contract_fail"
    assert any("impact_on_analysis" in error for error in report["schema_errors"])


def test_hzz_l3_contract_requires_mc_weighting_evidence(tmp_path):
    task = load_task_spec(HZZ_L3_DIR)
    (tmp_path / "four_lepton_mass_spectrum.json").write_text(
        json.dumps(
            {
                "observable": "m4l_GeV",
                "bin_edges": [120.0, 125.0, 130.0],
                "data_counts": [10.0, 14.0],
                "total_background_counts": [4.0, 5.0],
                "total_background_uncertainty": [2.0, 2.2],
                "signal_counts": [1.0, 2.0],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "four_lepton_excess_summary.json").write_text(
        json.dumps(
            {
                "method_type": "counting_window",
                "signal_region": [120.0, 130.0],
                "window_observed_yield": 24.0,
                "window_background_yield": 9.0,
                "window_signal_yield": 3.0,
                "window_numerator_yield": 15.0,
                "significance_proxy": 5.0,
                "significance_formula": "(N_obs - N_bkg)/sqrt(N_bkg)",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "interpretation.md").write_text("Minimal HZZ L3 contract fixture with no weighting evidence.", encoding="utf-8")
    (tmp_path / "submission_trace.json").write_text(
        json.dumps(
            {
                "workflow_stages": [{"stage_label": "analysis", "status": "completed"}],
                "execution_evidence": {
                    "files_processed_count": 1,
                    "events_processed_total": 10,
                    "selected_events_total": 1,
                    "candidates_built_total": 1,
                    "histogram_filled_entries": 1,
                },
                "scientific_decisions": [
                    {"decision": "count", "reason": "test", "impact_on_analysis": "test"}
                ],
                "input_samples_used": [{"sample_name": "Data", "sample_role": "data", "files_used": ["a.root"]}],
                "validation_checks": [{"validation_type": "non_empty_spectrum", "status": "passed", "result_summary": "ok"}],
                "observable_constructed": {"name": "m4l"},
                "inference_strategy": {"method_family": "counting_window"},
                "result_summary": {"conclusion": "fixture"},
                "output_files_generated": [
                    "four_lepton_mass_spectrum.json",
                    "four_lepton_excess_summary.json",
                    "interpretation.md",
                    "submission_trace.json",
                ],
            }
        ),
        encoding="utf-8",
    )

    report = validate_submission_dir(task, tmp_path)

    assert report["status"] == "contract_fail"
    assert any("mc_weighting_evidence" in error for error in report["schema_errors"])
