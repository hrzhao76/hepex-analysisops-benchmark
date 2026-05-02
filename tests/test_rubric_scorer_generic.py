import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from engine.rubric_scorer import score_submission


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_generic_l2_rubric_conditions_execute(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "fit_summary", "canonical_filename": "fit_summary.json", "type": "json"},
            {"name": "residual", "canonical_filename": "residual.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
        ],
        "optional_outputs": [],
        "schemas": {
            "fit_summary.json": {"required_fields": ["gaussian_mean_gev"]},
            "residual.json": {"required_fields": ["bin_centers", "residual_counts"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
            "submission_trace.json": {"required_fields": ["workflow_stages", "cuts_applied"]},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")

    trace = {
        "workflow_stages": [
            {"stage_id": "load_data", "family": "data_access", "order_index": 1},
            {"stage_id": "apply_photon_selection", "family": "object_or_event_selection", "order_index": 2},
            {"stage_id": "construct_diphoton_mass", "family": "observable_construction", "order_index": 3},
            {"stage_id": "histogram_spectrum", "family": "spectrum_or_summary_construction", "order_index": 4},
            {"stage_id": "fit_signal_background", "family": "inference_or_signal_localization", "order_index": 5},
            {"stage_id": "interpret_result", "family": "interpretation", "order_index": 6},
        ],
        "cuts_applied": [
            {"cut_id": "two_photons", "variable": "photon_count", "operator": ">=", "value": 2},
            {"cut_id": "tight_id", "variable": "photon_isTightID", "operator": "==", "value": True},
            {"cut_id": "pt", "variable": "photon_pt", "operator": ">", "value": 30.0},
            {"cut_id": "isolation", "variable": "photon_ptcone20", "operator": "<", "value": 0.055},
            {"cut_id": "eta_transition_veto", "variable": "abs_photon_eta", "operator": "interval_veto", "value": [1.37, 1.52]},
        ],
        "observable_constructed": {"name": "m_yy", "inputs": ["photon_pt", "photon_eta", "photon_phi", "photon_e"]},
        "fit_model_family_used": {"signal": "gaussian", "background": "polynomial"},
    }
    write_json(submission_dir / "fit_summary.json", {"gaussian_mean_gev": 125.1})
    write_json(submission_dir / "residual.json", {"bin_centers": [119.5, 124.5, 130.5], "residual_counts": [0.0, 2.0, 0.1]})
    write_json(submission_dir / "submission_trace.json", trace)
    (submission_dir / "interpretation.md").write_text("A localized excess is visible near 125 GeV.", encoding="utf-8")

    rubric = {
        "version": 1,
        "weights": {"execution": 0.2, "pipeline": 0.25, "implementation": 0.25, "analysis": 0.2, "validation": 0.1},
        "checks": {
            "execution": [
                {"id": "files", "type": "deterministic", "condition": {"required_files": ["fit_summary.json", "residual.json", "interpretation.md"]}, "score": 1.0}
            ],
            "pipeline": [
                {
                    "id": "families",
                    "type": "structural",
                    "condition": {
                        "trace_stage_families_present": {
                            "required_families": [
                                "data_access",
                                "object_or_event_selection",
                                "observable_construction",
                                "spectrum_or_summary_construction",
                                "inference_or_signal_localization",
                                "interpretation",
                            ]
                        }
                    },
                    "score": 0.5,
                },
                {
                    "id": "order",
                    "type": "structural",
                    "condition": {
                        "trace_stage_family_order": {
                            "ordered_families": [
                                "data_access",
                                "object_or_event_selection",
                                "observable_construction",
                                "spectrum_or_summary_construction",
                                "inference_or_signal_localization",
                                "interpretation",
                            ]
                        }
                    },
                    "score": 0.5,
                },
            ],
            "implementation": [
                {
                    "id": "selection",
                    "type": "structural",
                    "condition": {
                        "scientifically_valid_selection_evidence": {
                            "requires_minimum_photon_multiplicity": 2,
                            "requires_photon_quality_or_equivalent": True,
                            "requires_kinematic_reasonableness": True,
                            "requires_isolation_fraction_or_equivalent": True,
                            "requires_eta_transition_veto_or_equivalent": True,
                        }
                    },
                    "score": 1.0,
                }
            ],
            "analysis": [
                {
                    "id": "peak",
                    "type": "deterministic",
                    "condition": {"artifact_numeric_field_range": {"file": "fit_summary.json", "field": "gaussian_mean_gev", "expected_range": [123.0, 127.0]}},
                    "score": 0.5,
                },
                {
                    "id": "residual",
                    "type": "heuristic",
                    "condition": {"localized_excess_in_residual": {"file": "residual.json", "roi_gev": [120.0, 130.0]}},
                    "score": 0.5,
                },
            ],
            "validation": [
                {
                    "id": "trace_fields",
                    "type": "structural",
                    "condition": {"trace_required_fields": {"fields": ["workflow_stages", "cuts_applied"]}},
                    "score": 1.0,
                }
            ],
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hyy_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )
    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert report["final"]["normalized_score"] == 1.0
    assert {check["id"] for check in report["check_results"]} >= {"families", "selection", "peak", "residual"}


def test_l2_flexible_peak_and_histogram_checks_accept_non_gaussian_names(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
            {"name": "fit_summary", "canonical_filename": "fit_summary.json", "type": "json"},
            {"name": "residual", "canonical_filename": "residual.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
        ],
        "optional_outputs": [],
        "schemas": {
            "spectrum.json": {"required_fields": ["bin_edges_gev", "bin_counts"]},
            "fit_summary.json": {"required_fields": ["signal_peak_gev", "method_family"]},
            "residual.json": {"required_fields": ["bin_edges_gev", "residual_counts"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
            "submission_trace.json": {"required_fields": ["workflow_stages"]},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")

    write_json(
        submission_dir / "spectrum.json",
        {
            "bin_edges_gev": [100.0, 102.0, 104.0, 106.0, 108.0, 110.0],
            "bin_counts": [1, 2, 3, 2, 1],
        },
    )
    write_json(
        submission_dir / "fit_summary.json",
        {"method_family": "localized_signal_plus_smooth_background_fit", "signal_peak_gev": 125.2},
    )
    write_json(
        submission_dir / "residual.json",
        {"bin_edges_gev": [118.0, 122.0, 126.0, 130.0], "residual_counts": [0.1, 2.5, -0.1]},
    )
    write_json(
        submission_dir / "submission_trace.json",
        {"workflow_stages": [{"stage_label": "fit localized signal over smooth background", "family": "inference_or_signal_localization"}]},
    )
    (submission_dir / "interpretation.md").write_text("A localized excess is visible near 125 GeV.", encoding="utf-8")

    rubric = {
        "version": 1,
        "weights": {"analysis": 1.0},
        "checks": {
            "analysis": [
                {
                    "id": "histogram",
                    "type": "deterministic",
                    "condition": {
                        "artifact_histogram_properties": {
                            "file": "spectrum.json",
                            "range_gev_covers": [100.0, 110.0],
                            "bin_width_gev_between": [1.0, 2.5],
                            "min_bins": 5,
                        }
                    },
                    "score": 0.34,
                },
                {
                    "id": "peak",
                    "type": "deterministic",
                    "condition": {
                        "artifact_numeric_field_range": {
                            "file": "fit_summary.json",
                            "field": "signal_peak_gev",
                            "expected_range": [123.0, 127.0],
                        }
                    },
                    "score": 0.33,
                },
                {
                    "id": "residual",
                    "type": "heuristic",
                    "condition": {"localized_excess_in_residual": {"file": "residual.json", "roi_gev": [120.0, 130.0]}},
                    "score": 0.33,
                },
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hyy_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert report["final"]["normalized_score"] == 1.0
    assert all(check["passed"] for check in report["check_results"])


def test_l2_selection_evidence_accepts_crack_exclusion_wording(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {"required_fields": ["workflow_stages", "selection_strategy"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "workflow_stages": [
                {"stage_label": "Load files", "family": "data_access"},
                {"stage_label": "Build mass", "family": "observable_construction"},
                {"stage_label": "Build spectrum", "family": "spectrum_or_summary_construction"},
            ],
            "selection_strategy": {
                "photon_quality": "Require photon_isTightID == True.",
                "kinematics": {"leading_pt_min_gev": 35.0},
                "eta_region": {"exclude_crack": [1.37, 1.52]},
                "isolation": {"ptcone20_max_gev": 5.0},
                "event_requirement": "At least two selected photons.",
            },
        },
    )
    (submission_dir / "interpretation.md").write_text("Trace-only fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"implementation": 1.0},
        "checks": {
            "implementation": [
                {
                    "id": "selection",
                    "type": "structural",
                    "condition": {
                        "scientifically_valid_selection_evidence": {
                            "requires_minimum_photon_multiplicity": 2,
                            "requires_photon_quality_or_equivalent": True,
                            "requires_kinematic_reasonableness": True,
                            "requires_isolation_fraction_or_equivalent": True,
                            "requires_eta_transition_veto_or_equivalent": True,
                        }
                    },
                    "score": 1.0,
                }
            ],
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hyy_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert report["check_results"][0]["passed"]


def test_stage_family_order_does_not_confuse_observable_and_spectrum_construction(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {"required_fields": ["workflow_stages"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "workflow_stages": [
                {"stage_label": "Build mass", "family": "observable_construction"},
                {"stage_label": "Load files", "family": "data_access"},
                {"stage_label": "Build spectrum", "family": "spectrum_or_summary_construction"},
            ]
        },
    )
    (submission_dir / "interpretation.md").write_text("Order fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"pipeline": 1.0},
        "checks": {
            "pipeline": [
                {
                    "id": "order",
                    "type": "structural",
                    "condition": {
                        "trace_stage_family_order": {
                            "ordered_families": [
                                "data_access",
                                "observable_construction",
                                "spectrum_or_summary_construction",
                            ]
                        }
                    },
                    "score": 1.0,
                }
            ],
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hyy_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert not report["check_results"][0]["passed"]


def test_data_scope_accepts_year_periods_from_input_filenames(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {"required_fields": ["data_scope"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "data_scope": {
                "release": "2025e-13tev-beta",
                "dataset": "data",
                "skim": "GamGam",
                "files_combined": True,
                "periods_used": ["periodD", "periodA"],
                "input_files_used": [
                    "ODEO_FEB2025_v0_GamGam_data15_periodD.GamGam.root",
                    "ODEO_FEB2025_v0_GamGam_data16_periodA.GamGam.root",
                ],
            }
        },
    )
    (submission_dir / "interpretation.md").write_text("Data scope fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"pipeline": 1.0},
        "checks": {
            "pipeline": [
                {
                    "id": "scope",
                    "type": "structural",
                    "condition": {
                        "trace_data_scope_coverage": {
                            "required_dataset": {
                                "sample": "GamGam",
                                "periods": ["2015_D", "2016_A"],
                            }
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hyy_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert report["check_results"][0]["passed"]
    assert report["check_results"][0]["evidence"]["normalized_periods"] == ["2015_d", "2016_a"]


def test_mass_dependent_selection_accepts_pt_over_myy_wording(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {"required_fields": ["selection_strategy", "inference_strategy"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "selection_strategy": {
                "requirements": {
                    "kinematics": "leading photon pT > 40 GeV and subleading photon pT > 30 GeV before m_yy scaling cuts",
                    "mass_scaled_pt": "leading pT/m_yy > 0.35 and subleading pT/m_yy > 0.25",
                }
            },
            "inference_strategy": {
                "fit_localization_range_gev": [100.0, 160.0],
                "signal_scan_window_gev": [120.0, 130.0],
            },
        },
    )
    (submission_dir / "interpretation.md").write_text("Mass-dependent selection fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"implementation": 1.0},
        "checks": {
            "implementation": [
                {
                    "id": "mass_scaled",
                    "type": "structural",
                    "condition": {
                        "trace_mass_dependent_selection": {
                            "requires_mass_computed_before_mass_scaled_cut": True,
                            "requires_mass_nonzero_handling": True,
                            "requires_pt_over_mass_requirement_or_equivalent": True,
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hyy_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    check = report["check_results"][0]
    assert check["passed"]
    assert check["evidence"]["ratio_evidence"]
    assert check["evidence"]["positive_mass_window"]
