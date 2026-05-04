import json
from pathlib import Path
from types import SimpleNamespace

import pytest
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


def test_selection_cuts_accept_variable_aliases_and_operator_synonyms(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l1",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {"required_fields": ["cuts_applied"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "cuts_applied": [
                {
                    "cut_id": "event_trigger_requirement",
                    "variable": "trigE OR trigM",
                    "operator": "==",
                    "value": True,
                },
                {
                    "cut_id": "four_lepton_flavor_requirement",
                    "variable": "sum(lep_type[0:4])",
                    "operator": "in",
                    "value": [44, 48, 52],
                },
            ]
        },
    )
    (submission_dir / "interpretation.md").write_text("Trace-only fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"implementation": 1.0},
        "checks": {
            "implementation": [
                {
                    "id": "selection_cuts",
                    "type": "deterministic",
                    "condition": {
                        "selection_cuts": [
                            {
                                "cut_id": "event_trigger_requirement",
                                "variable_any_of": ["event_trigger_pass", "trigE OR trigM"],
                                "operator": "==",
                                "value": True,
                            },
                            {
                                "cut_id": "four_lepton_flavor_requirement",
                                "variable_any_of": ["sum_lep_type", "sum(lep_type[0:4])"],
                                "operator": "in_set",
                                "value": [44, 48, 52],
                            },
                        ]
                    },
                    "score": 1.0,
                }
            ],
        },
    }
    task = SimpleNamespace(
        id="generic_l1",
        type="hzz4l_l1",
        level="l1",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert report["check_results"][0]["passed"]


def test_hzz_selection_cuts_accept_equivalent_trace_expressions(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l1",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {"required_fields": ["cuts_applied"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "cuts_applied": [
                {
                    "cut_id": "typed_lepton_quality_requirement",
                    "variable": "count((mu medium and looseIso) or (e looseID and looseIso)) over first four leptons",
                    "operator": "==",
                    "value": 4,
                },
                {
                    "cut_id": "four_lepton_flavor_requirement",
                    "variable": "lep_type[0]+lep_type[1]+lep_type[2]+lep_type[3]",
                    "operator": "in",
                    "value": [44, 48, 52],
                },
                {
                    "cut_id": "total_charge_requirement",
                    "variable": "lep_charge[0]+lep_charge[1]+lep_charge[2]+lep_charge[3]",
                    "operator": "==",
                    "value": 0,
                },
            ]
        },
    )
    (submission_dir / "interpretation.md").write_text("Trace-only HZZ fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"implementation": 1.0},
        "checks": {
            "implementation": [
                {
                    "id": "selection_cuts",
                    "type": "deterministic",
                    "condition": {
                        "selection_cuts": [
                            {
                                "cut_id": "typed_lepton_quality_requirement",
                                "variable_any_of": [
                                    "typed_quality_lepton_count",
                                    "count((lep_type==13 and lep_isMediumID and lep_isLooseIso) or (lep_type==11 and lep_isLooseID and lep_isLooseIso))",
                                ],
                                "operator": "==",
                                "value": 4,
                            },
                            {
                                "cut_id": "four_lepton_flavor_requirement",
                                "variable_any_of": ["sum_lep_type", "sum(lep_type[0:4])"],
                                "operator": "in_set",
                                "value": [44, 48, 52],
                            },
                            {
                                "cut_id": "total_charge_requirement",
                                "variable_any_of": ["total_lepton_charge", "sum(lep_charge[0:4])"],
                                "operator": "==",
                                "value": 0,
                            },
                        ]
                    },
                    "score": 1.0,
                }
            ],
        },
    }
    task = SimpleNamespace(
        id="t005_hzz4l_l1",
        type="hzz4l_l1",
        level="l1",
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


def test_l2_stage_families_are_inferred_from_semantic_trace_fields(tmp_path):
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
                {"stage_label": "manifest_ingest", "status": "completed"},
                {"stage_label": "four_lepton_selection", "status": "completed"},
                {"stage_label": "m4l_reconstruction_and_histogramming", "status": "completed"},
                {"stage_label": "counting_window_excess_assessment", "status": "completed"},
            ],
            "scientific_decisions": [
                "Kept data unweighted and weighted MC with mcWeight times scale factors times xsec*filteff*kfac*36.6 fb^-1 divided by sum_of_weights."
            ],
            "output_files_generated": ["four_lepton_mass_spectrum.json", "interpretation.md", "submission_trace.json"],
        },
    )
    (submission_dir / "interpretation.md").write_text("Semantic stage fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"pipeline": 1.0},
        "checks": {
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
                                "event_weighting",
                                "spectrum_or_summary_construction",
                                "inference_or_signal_localization",
                                "interpretation",
                            ],
                            "minimum_pass_fraction": 0.75,
                        }
                    },
                    "score": 0.5,
                },
                {
                    "id": "order",
                    "type": "structural",
                    "condition": {
                        "trace_stage_family_order": {
                            "required_partial_orders": [
                                {"before": "data_access", "after": "object_or_event_selection"},
                                {"before": "object_or_event_selection", "after": "observable_construction"},
                                {"before": "observable_construction", "after": "spectrum_or_summary_construction"},
                                {"before": "event_weighting", "after": "spectrum_or_summary_construction"},
                                {"before": "spectrum_or_summary_construction", "after": "inference_or_signal_localization"},
                                {"before": "inference_or_signal_localization", "after": "interpretation"},
                            ],
                            "ignore_missing_families": True,
                            "allow_same_stage": True,
                        }
                    },
                    "score": 0.5,
                },
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert all(check["passed"] for check in report["check_results"])
    families = report["check_results"][0]["evidence"]["families"]
    assert "observable_construction" in families
    assert "spectrum_or_summary_construction" in families
    assert "inference_or_signal_localization" in families


def test_l2_selection_and_weighting_accept_natural_language_evidence(tmp_path):
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
            "submission_trace.json": {"required_fields": ["scientific_decisions"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "scientific_decisions": [
                "Applied trigger requirement trigE or trigM, total charge zero for the first four leptons, ordered pT thresholds of 25, 15, 10, and 7 GeV, and simple electron tight-ID / muon loose-isolation quality requirements.",
                "Kept data unweighted and weighted MC with mcWeight times scale factors times xsec*filteff*kfac*36.6 fb^-1 divided by sum_of_weights.",
            ],
            "observable_constructed": {"name": "m4l from first four leptons"},
        },
    )
    (submission_dir / "interpretation.md").write_text("Selection and weighting fixture.", encoding="utf-8")
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
                            "required_component_groups": ["trigger", "kinematic", "object_quality", "isolation", "topology", "charge"],
                            "minimum_groups": 5,
                        }
                    },
                    "score": 0.5,
                },
                {
                    "id": "weighting",
                    "type": "structural",
                    "condition": {
                        "mc_weighting_strategy": {
                            "data_policy": "unweighted",
                            "mc_policy": "weighted_and_luminosity_normalized",
                            "luminosity_fb_inv": 36.6,
                            "required_mc_factors": [
                                "sum_of_weights",
                                "mcWeight",
                                "xsec",
                                "filteff",
                                "kfac",
                                "ScaleFactor_PILEUP",
                                "ScaleFactor_ELE",
                                "ScaleFactor_MUON",
                                "ScaleFactor_LepTRIGGER",
                            ],
                        }
                    },
                    "score": 0.5,
                },
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert all(check["passed"] for check in report["check_results"])


def test_mc_weighting_strategy_accepts_structured_mc_weighting_evidence(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l3",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {"required_fields": ["mc_weighting_evidence"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "mc_weighting_evidence": {
                "data_policy": "data samples are unweighted",
                "mc_policy": "MC backgrounds and signal are weighted and luminosity normalized",
                "luminosity_fb_inv": 36.6,
                "weight_formula": "36.6 * 1000 * xsec * filteff * kfac * mcWeight * ScaleFactor_PILEUP * ScaleFactor_ELE * ScaleFactor_MUON * ScaleFactor_LepTRIGGER / sum_of_weights",
                "event_weight_factors_used": ["mcWeight"],
                "sample_normalization_fields": ["xsec", "filteff", "kfac", "sum_of_weights"],
                "scale_factors_used": [
                    "ScaleFactor_PILEUP",
                    "ScaleFactor_ELE",
                    "ScaleFactor_MUON",
                    "ScaleFactor_LepTRIGGER",
                ],
                "missing_fields": [],
                "fallback_strategy": "none",
                "uncertainty_policy": "background bin uncertainty uses sqrt(sum w^2)",
            }
        },
    )
    (submission_dir / "interpretation.md").write_text("Structured weighting fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"implementation": 1.0},
        "checks": {
            "implementation": [
                {
                    "id": "structured_weighting",
                    "type": "structural",
                    "condition": {
                        "mc_weighting_strategy": {
                            "required_evidence_field": "mc_weighting_evidence",
                            "require_structured_evidence": True,
                            "data_policy": "unweighted",
                            "mc_policy": "weighted_and_luminosity_normalized",
                            "luminosity_fb_inv": 36.6,
                            "required_mc_factors": [
                                "sum_of_weights",
                                "mcWeight",
                                "xsec",
                                "filteff",
                                "kfac",
                                "ScaleFactor_PILEUP",
                                "ScaleFactor_ELE",
                                "ScaleFactor_MUON",
                                "ScaleFactor_LepTRIGGER",
                            ],
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l3",
        type="hzz4l_l3",
        level="l3",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert report["check_results"][0]["passed"]
    assert report["check_results"][0]["evidence"]["structured_evidence_present"] is True


def test_mc_weighting_strategy_rejects_vague_text_when_structured_evidence_required(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l3",
        "required_outputs": [
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "submission_trace.json": {"required_fields": ["scientific_decisions"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "scientific_decisions": [
                {"decision": "Use standard weighting", "reason": "MC must be comparable to data", "impact_on_analysis": "normalizes templates"}
            ]
        },
    )
    (submission_dir / "interpretation.md").write_text("Vague weighting fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"implementation": 1.0},
        "checks": {
            "implementation": [
                {
                    "id": "structured_weighting",
                    "type": "structural",
                    "condition": {
                        "mc_weighting_strategy": {
                            "required_evidence_field": "mc_weighting_evidence",
                            "require_structured_evidence": True,
                            "data_policy": "unweighted",
                            "mc_policy": "weighted_and_luminosity_normalized",
                            "required_mc_factors": ["sum_of_weights", "mcWeight", "xsec"],
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l3",
        type="hzz4l_l3",
        level="l3",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert not report["check_results"][0]["passed"]
    assert "missing_structured_evidence:mc_weighting_evidence" in report["check_results"][0]["evidence"]["missing"]


def test_validation_evidence_can_come_from_trace_validation_checks(tmp_path):
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
            "submission_trace.json": {"required_fields": ["validation_checks"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "submission_trace.json",
        {
            "validation_checks": [
                {"check_id": "sideband_check", "result": "sidebands are consistent with the background trend."}
            ]
        },
    )
    (submission_dir / "interpretation.md").write_text("Validation fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"validation": 1.0},
        "checks": {
            "validation": [
                {
                    "id": "validation",
                    "type": "structural",
                    "condition": {
                        "validation_evidence_any": {
                            "allowed_validation_types": ["sideband_check", "alternative_binning_check"],
                            "minimum_count": 1,
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert report["check_results"][0]["passed"]


def test_artifact_window_consistency_rejects_high_significance_without_validation(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
            {"name": "summary", "canonical_filename": "summary.json", "type": "json"},
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "spectrum.json": {"required_fields": ["bin_edges", "data_counts", "total_background_counts"]},
            "summary.json": {"required_fields": ["signal_region", "window_background_yield", "significance_proxy"]},
            "submission_trace.json": {"required_fields": ["workflow_stages"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "spectrum.json",
        {
            "bin_edges": [120.0, 125.0, 130.0],
            "data_counts": [43.0, 39.0],
            "total_background_counts": [28.880309923717107, 1.281450367729235],
            "signal_counts": [18.27265998763747, 13.3927022139031],
        },
    )
    write_json(
        submission_dir / "summary.json",
        {
            "signal_region": [120.0, 130.0],
            "window_background_yield": 30.161760291446342,
            "window_numerator_yield": 61.82712249298691,
            "significance_proxy": 9.438911270197902,
        },
    )
    write_json(submission_dir / "submission_trace.json", {"workflow_stages": [{"stage_label": "counting_window_excess_assessment"}]})
    (submission_dir / "interpretation.md").write_text("A high-significance excess is claimed.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"analysis": 1.0},
        "checks": {
            "analysis": [
                {
                    "id": "window",
                    "type": "deterministic",
                    "condition": {
                        "artifact_window_consistency": {
                            "spectrum_file": "spectrum.json",
                            "summary_file": "summary.json",
                            "signal_region": [120.0, 130.0],
                            "data_field": "data_counts",
                            "background_field": "total_background_counts",
                            "signal_field": "signal_counts",
                            "summary_background_field": "window_background_yield",
                            "summary_numerator_field": "window_numerator_yield",
                            "summary_numerator_policy": "background_plus_signal",
                            "significance_field": "significance_proxy",
                            "validation_required_above_significance": 5.0,
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    check = report["check_results"][0]
    assert not check["passed"]
    assert check["evidence"]["failures"][0]["reason"] == "high_significance_without_validation_evidence"


def test_artifact_window_consistency_accepts_signal_template_significance_formula(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
            {"name": "summary", "canonical_filename": "summary.json", "type": "json"},
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "spectrum.json": {"required_fields": ["bin_edges", "data_counts", "total_background_counts", "signal_counts"]},
            "summary.json": {"required_fields": ["signal_region", "window_background_yield", "window_numerator_yield", "significance_proxy"]},
            "submission_trace.json": {"required_fields": ["workflow_stages"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "spectrum.json",
        {
            "bin_edges": [120.0, 125.0, 130.0],
            "data_counts": [700.0, 819.0],
            "total_background_counts": [95.55229949951172, 95.48033142089844],
            "signal_counts": [14.569772720336914, 11.395055770874023],
        },
    )
    write_json(
        submission_dir / "summary.json",
        {
            "signal_region": [120.0, 130.0],
            "window_background_yield": 191.03263092041016,
            "window_numerator_yield": 216.9974594116211,
            "significance_proxy": 1.8783848803250128,
        },
    )
    write_json(submission_dir / "submission_trace.json", {"workflow_stages": [{"stage_label": "counting_window_excess_assessment"}]})
    (submission_dir / "interpretation.md").write_text("Signal-template significance fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"analysis": 1.0},
        "checks": {
            "analysis": [
                {
                    "id": "window",
                    "type": "deterministic",
                    "condition": {
                        "artifact_window_consistency": {
                            "spectrum_file": "spectrum.json",
                            "summary_file": "summary.json",
                            "signal_region": [120.0, 130.0],
                            "data_field": "data_counts",
                            "background_field": "total_background_counts",
                            "signal_field": "signal_counts",
                            "summary_background_field": "window_background_yield",
                            "summary_numerator_field": "window_numerator_yield",
                            "summary_numerator_policy": "background_plus_signal",
                            "significance_field": "significance_proxy",
                            "significance_formula": "numerator_minus_background_over_sqrt_background",
                            "significance_absolute_tolerance": 0.01,
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    check = report["check_results"][0]
    assert check["passed"]
    assert check["evidence"]["expected_significance"] == pytest.approx(1.878, abs=0.01)


def test_artifact_window_consistency_accepts_declared_data_minus_background_formula_alias(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l3",
        "required_outputs": [
            {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
            {"name": "summary", "canonical_filename": "summary.json", "type": "json"},
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
        ],
        "optional_outputs": [],
        "schemas": {
            "spectrum.json": {"required_fields": ["bin_edges", "data_counts", "total_background_counts", "signal_counts"]},
            "summary.json": {
                "required_fields": [
                    "signal_region",
                    "window_observed_yield",
                    "window_background_yield",
                    "window_numerator_yield",
                    "significance_proxy",
                    "significance_formula",
                ]
            },
            "submission_trace.json": {"required_fields": ["validation_checks"]},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "spectrum.json",
        {
            "bin_edges": [120.0, 125.0, 130.0],
            "data_counts": [10.0, 14.0],
            "total_background_counts": [4.0, 5.0],
            "signal_counts": [1.0, 2.0],
        },
    )
    write_json(
        submission_dir / "summary.json",
        {
            "signal_region": [120.0, 130.0],
            "window_observed_yield": 24.0,
            "window_background_yield": 9.0,
            "window_signal_yield": 3.0,
            "window_numerator_yield": 15.0,
            "significance_proxy": 5.0,
            "significance_formula": "(N_obs - N_bkg)/sqrt(N_bkg)",
        },
    )
    write_json(
        submission_dir / "submission_trace.json",
        {"validation_checks": [{"validation_type": "signal_window_sanity", "status": "passed", "result_summary": "ok"}]},
    )
    rubric = {
        "version": 1,
        "weights": {"analysis": 1.0},
        "checks": {
            "analysis": [
                {
                    "id": "window",
                    "type": "deterministic",
                    "condition": {
                        "artifact_window_consistency": {
                            "spectrum_file": "spectrum.json",
                            "summary_file": "summary.json",
                            "signal_region": [120.0, 130.0],
                            "data_field": "data_counts",
                            "background_field": "total_background_counts",
                            "signal_field": "signal_counts",
                            "summary_data_field": "window_observed_yield",
                            "summary_background_field": "window_background_yield",
                            "summary_signal_field": "window_signal_yield",
                            "summary_numerator_field": "window_numerator_yield",
                            "summary_numerator_policy": "declared_formula_numerator",
                            "significance_field": "significance_proxy",
                            "significance_formula": "declared_supported_formula",
                            "summary_significance_formula_field": "significance_formula",
                            "allowed_significance_formulas": ["data_minus_background_over_sqrt_background"],
                            "significance_absolute_tolerance": 0.01,
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l3",
        type="hzz4l_l3",
        level="l3",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    check = report["check_results"][0]
    assert check["passed"]
    assert check["evidence"]["expected_numerator_yield"] == pytest.approx(15.0)
    assert check["evidence"]["expected_significance"] == pytest.approx(5.0)


def test_artifact_window_consistency_accepts_declared_background_variance_formula(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l3",
        "required_outputs": [
            {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
            {"name": "summary", "canonical_filename": "summary.json", "type": "json"},
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
        ],
        "optional_outputs": [],
        "schemas": {
            "spectrum.json": {"required_fields": ["bin_edges", "data_counts", "total_background_counts", "total_background_uncertainty"]},
            "summary.json": {
                "required_fields": [
                    "signal_region",
                    "window_observed_yield",
                    "window_background_yield",
                    "window_numerator_yield",
                    "significance_proxy",
                    "significance_formula",
                ]
            },
            "submission_trace.json": {"required_fields": ["validation_checks"]},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(
        submission_dir / "spectrum.json",
        {
            "bin_edges": [120.0, 125.0, 130.0],
            "data_counts": [10.0, 14.0],
            "total_background_counts": [4.0, 5.0],
            "total_background_uncertainty": [2.0, 3.0],
        },
    )
    expected_significance = 15.0 / ((9.0 + 13.0) ** 0.5)
    write_json(
        submission_dir / "summary.json",
        {
            "signal_region": [120.0, 130.0],
            "window_observed_yield": 24.0,
            "window_background_yield": 9.0,
            "window_numerator_yield": 15.0,
            "significance_proxy": expected_significance,
            "significance_formula": "(N_obs - N_bkg) / sqrt(N_bkg + sum_i w_i^2)",
        },
    )
    write_json(
        submission_dir / "submission_trace.json",
        {"validation_checks": [{"validation_type": "signal_window_sanity", "status": "passed", "result_summary": "ok"}]},
    )
    rubric = {
        "version": 1,
        "weights": {"analysis": 1.0},
        "checks": {
            "analysis": [
                {
                    "id": "window",
                    "type": "deterministic",
                    "condition": {
                        "artifact_window_consistency": {
                            "spectrum_file": "spectrum.json",
                            "summary_file": "summary.json",
                            "signal_region": [120.0, 130.0],
                            "data_field": "data_counts",
                            "background_field": "total_background_counts",
                            "background_uncertainty_field": "total_background_uncertainty",
                            "summary_data_field": "window_observed_yield",
                            "summary_background_field": "window_background_yield",
                            "summary_numerator_field": "window_numerator_yield",
                            "summary_numerator_policy": "declared_formula_numerator",
                            "significance_field": "significance_proxy",
                            "significance_formula": "declared_supported_formula",
                            "summary_significance_formula_field": "significance_formula",
                            "allowed_significance_formulas": ["data_minus_background_over_sqrt_background_plus_variance"],
                            "significance_absolute_tolerance": 0.01,
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l3",
        type="hzz4l_l3",
        level="l3",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    check = report["check_results"][0]
    assert check["passed"]
    assert check["evidence"]["derived_background_variance"] == pytest.approx(13.0)
    assert check["evidence"]["expected_significance"] == pytest.approx(expected_significance)


def test_trace_execution_evidence_rejects_zero_counters(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "spectrum.json": {"required_fields": ["bin_edges", "data_counts"]},
            "submission_trace.json": {"required_fields": ["execution_evidence"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(submission_dir / "input_manifest.json", {"files": [{"path": "a.root"}, {"path": "b.root"}]})
    write_json(submission_dir / "spectrum.json", {"bin_edges": [120.0, 130.0], "data_counts": [1.0]})
    write_json(
        submission_dir / "submission_trace.json",
        {
            "execution_evidence": {
                "files_processed_count": 0,
                "events_processed_total": 0,
                "selected_events_total": 0,
                "candidates_built_total": 0,
                "histogram_filled_entries": 0,
            }
        },
    )
    (submission_dir / "interpretation.md").write_text("Execution evidence fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"execution": 1.0},
        "checks": {
            "execution": [
                {
                    "id": "execution_evidence",
                    "type": "deterministic",
                    "condition": {
                        "trace_execution_evidence_consistency": {
                            "input_manifest_file": "input_manifest.json",
                            "required_positive_fields": [
                                "files_processed_count",
                                "events_processed_total",
                                "selected_events_total",
                                "candidates_built_total",
                                "histogram_filled_entries",
                            ],
                            "require_files_processed_at_least_manifest_count": True,
                            "spectrum_file": "spectrum.json",
                            "histogram_positive_series_fields": ["data_counts"],
                            "histogram_count_must_cover_series_field": "data_counts",
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    check = report["check_results"][0]
    assert not check["passed"]
    assert any(failure["reason"] == "expected_positive" for failure in check["evidence"]["failures"])
    assert any(failure["reason"] == "less_than_manifest_file_count" for failure in check["evidence"]["failures"])


def test_artifact_series_usable_requires_positive_sum_and_bin_alignment(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "spectrum.json": {"required_fields": ["bin_edges", "data_counts"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    write_json(submission_dir / "spectrum.json", {"bin_edges": [80.0, 85.0, 90.0], "data_counts": [0.0, 0.0]})
    (submission_dir / "interpretation.md").write_text("Series fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"analysis": 1.0},
        "checks": {
            "analysis": [
                {
                    "id": "series",
                    "type": "deterministic",
                    "condition": {
                        "artifact_series_usable": {
                            "file": "spectrum.json",
                            "field": "data_counts",
                            "requirements": ["nonempty", "finite_values", "nonnegative_values", "positive_sum", "aligned_with_bin_edges"],
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    check = report["check_results"][0]
    assert not check["passed"]
    assert "positive_sum" in check["evidence"]["failures"]


def test_artifact_window_consistency_accepts_reference_style_hzz_formula(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    contract = {
        "version": 1,
        "level": "l2",
        "required_outputs": [
            {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
            {"name": "summary", "canonical_filename": "summary.json", "type": "json"},
            {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
            {"name": "interpretation", "canonical_filename": "interpretation.md", "type": "markdown"},
        ],
        "optional_outputs": [],
        "schemas": {
            "spectrum.json": {"required_fields": ["bin_edges", "data_counts", "total_background_counts", "signal_counts"]},
            "summary.json": {"required_fields": ["signal_region", "window_background_yield", "window_signal_yield", "window_numerator_yield", "significance_proxy"]},
            "submission_trace.json": {"required_fields": ["validation_checks"]},
            "interpretation.md": {"constraints": {"non_empty": True}},
        },
    }
    (task_dir / "submission_contract.yaml").write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    background = 10.300928
    signal = 19.009814
    observed = 29.0
    numerator = background + signal
    significance = numerator / ((background + 0.3 * background * background) ** 0.5)
    write_json(
        submission_dir / "spectrum.json",
        {
            "bin_edges": [120.0, 122.5, 130.0],
            "data_counts": [0.0, observed],
            "total_background_counts": [0.0, background],
            "signal_counts": [0.0, signal],
        },
    )
    write_json(
        submission_dir / "summary.json",
        {
            "signal_region": [122.5, 130.0],
            "window_observed_yield": observed,
            "window_background_yield": background,
            "window_signal_yield": signal,
            "window_numerator_yield": numerator,
            "significance_proxy": significance,
        },
    )
    write_json(
        submission_dir / "submission_trace.json",
        {"validation_checks": [{"validation_type": "signal_window_sanity_check", "status": "passed", "result_summary": "ok"}]},
    )
    (submission_dir / "interpretation.md").write_text("Reference-style HZZ formula fixture.", encoding="utf-8")
    rubric = {
        "version": 1,
        "weights": {"analysis": 1.0},
        "checks": {
            "analysis": [
                {
                    "id": "window",
                    "type": "deterministic",
                    "condition": {
                        "artifact_window_consistency": {
                            "spectrum_file": "spectrum.json",
                            "summary_file": "summary.json",
                            "signal_region": [122.5, 130.0],
                            "data_field": "data_counts",
                            "background_field": "total_background_counts",
                            "signal_field": "signal_counts",
                            "summary_data_field": "window_observed_yield",
                            "summary_background_field": "window_background_yield",
                            "summary_signal_field": "window_signal_yield",
                            "summary_numerator_field": "window_numerator_yield",
                            "summary_numerator_policy": "background_plus_signal",
                            "significance_field": "significance_proxy",
                            "significance_formula": "numerator_over_sqrt_background_plus_fractional_systematic",
                            "background_systematic_fraction": 0.3,
                            "significance_absolute_tolerance": 0.01,
                            "required_positive_window_yields": ["data", "background", "signal", "numerator", "significance"],
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    check = report["check_results"][0]
    assert check["passed"]
    assert check["evidence"]["expected_significance"] == pytest.approx(4.5156, abs=0.01)


def test_validation_evidence_alias_groups_match_hzz_l2_trace_names(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    (task_dir / "submission_contract.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "level": "l2",
                "required_outputs": [
                    {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"}
                ],
                "schemas": {"submission_trace.json": {"required_fields": ["validation_checks"]}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    write_json(
        submission_dir / "submission_trace.json",
        {
            "validation_checks": [
                {
                    "validation_type": "non_empty_selected_sample",
                    "status": "passed",
                    "result_summary": "Selected events total was non-zero.",
                },
                {
                    "validation_type": "spectrum_array_alignment",
                    "status": "passed",
                    "result_summary": "Bin edges and spectrum arrays are aligned.",
                },
                {
                    "validation_type": "signal_window_consistency",
                    "status": "passed",
                    "result_summary": "Signal window yields agree with the spectrum.",
                },
                {
                    "validation_type": "weighting_sanity",
                    "status": "warning",
                    "result_summary": "MC normalization scale is suspicious.",
                },
            ]
        },
    )
    rubric = {
        "version": 1,
        "weights": {"validation": 1.0},
        "checks": {
            "validation": [
                {
                    "id": "validation",
                    "type": "structural",
                    "condition": {
                        "validation_evidence_any": {
                            "minimum_count": 3,
                            "minimum_group_count": 3,
                            "validation_type_aliases": {
                                "selected_yield": ["nonzero_event_yield", "non_empty_selected_sample"],
                                "spectrum_integrity": ["nonempty_m4l_spectrum", "spectrum_array_alignment"],
                                "signal_window_sanity": ["signal_window_sanity_check", "signal_window_consistency"],
                                "weighting_sanity": ["weighting_sanity", "mc normalization"],
                            },
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})
    check = report["check_results"][0]

    assert check["passed"]
    assert set(check["evidence"]["matched_groups"]) >= {
        "selected_yield",
        "spectrum_integrity",
        "signal_window_sanity",
        "weighting_sanity",
    }


def test_artifact_series_scale_plausibility_passes_reasonable_data_mc_scale(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    (task_dir / "submission_contract.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "level": "l2",
                "required_outputs": [{"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"}],
                "schemas": {"spectrum.json": {"required_fields": ["bin_edges", "data_counts", "total_background_counts"]}},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    write_json(
        submission_dir / "spectrum.json",
        {
            "bin_edges": [80.0, 120.0, 125.0, 130.0, 250.0],
            "data_counts": [20.0, 10.0, 12.0, 30.0],
            "total_background_counts": [18.0, 9.0, 11.0, 34.0],
        },
    )
    rubric = {
        "version": 1,
        "weights": {"analysis": 1.0},
        "checks": {
            "analysis": [
                {
                    "id": "scale",
                    "type": "deterministic",
                    "condition": {
                        "artifact_series_scale_plausibility": {
                            "file": "spectrum.json",
                            "observed_field": "data_counts",
                            "expected_field": "total_background_counts",
                            "regions": [
                                {"name": "full", "interval": [80.0, 250.0]},
                                {"name": "roi", "interval": [120.0, 130.0]},
                            ],
                            "expected_over_observed_sum_range": [0.01, 100.0],
                            "max_expected_over_observed_bin_ratio": 1000.0,
                        }
                    },
                    "score": 1.0,
                }
            ]
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})

    assert report["check_results"][0]["passed"]


def test_artifact_series_scale_plausibility_flags_order_of_magnitude_mc_blowup(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    (task_dir / "submission_contract.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "level": "l2",
                "required_outputs": [
                    {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
                    {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
                ],
                "schemas": {
                    "spectrum.json": {"required_fields": ["bin_edges", "data_counts", "total_background_counts"]},
                    "submission_trace.json": {"required_fields": ["validation_checks"]},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    write_json(
        submission_dir / "spectrum.json",
        {
            "bin_edges": [80.0, 120.0, 125.0, 130.0, 250.0],
            "data_counts": [1000.0, 500.0, 500.0, 1000.0],
            "total_background_counts": [1.0e9, 8.0e8, 8.0e8, 1.0e9],
        },
    )
    write_json(
        submission_dir / "submission_trace.json",
        {
            "validation_checks": [
                {
                    "validation_type": "weighting_sanity",
                    "status": "warning",
                    "result_summary": "MC normalization scale is suspicious.",
                }
            ]
        },
    )
    rubric = {
        "version": 1,
        "weights": {"analysis": 1.0, "validation": 1.0},
        "checks": {
            "analysis": [
                {
                    "id": "scale",
                    "type": "deterministic",
                    "condition": {
                        "artifact_series_scale_plausibility": {
                            "file": "spectrum.json",
                            "observed_field": "data_counts",
                            "expected_field": "total_background_counts",
                            "regions": [{"name": "roi", "interval": [120.0, 130.0]}],
                            "expected_over_observed_sum_range": [0.01, 100.0],
                            "max_expected_over_observed_bin_ratio": 1000.0,
                        }
                    },
                    "score": 1.0,
                }
            ],
            "validation": [
                {
                    "id": "validation",
                    "type": "structural",
                    "condition": {
                        "validation_evidence_any": {
                            "minimum_count": 1,
                            "minimum_group_count": 1,
                            "validation_type_aliases": {"weighting_sanity": ["weighting_sanity"]},
                        }
                    },
                    "score": 1.0,
                }
            ],
        },
    }
    task = SimpleNamespace(
        id="generic_l2",
        type="hzz4l_l2",
        level="l2",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})
    checks = {check["id"]: check for check in report["check_results"]}

    assert not checks["scale"]["passed"]
    assert checks["validation"]["passed"]


def test_l3_open_strategy_trace_passes_but_missing_125gev_localization_is_penalized(tmp_path):
    task_dir = tmp_path / "task"
    submission_dir = tmp_path / "submission"
    task_dir.mkdir()
    submission_dir.mkdir()
    (task_dir / "submission_contract.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "level": "l3",
                "required_outputs": [
                    {"name": "spectrum", "canonical_filename": "spectrum.json", "type": "json"},
                    {"name": "submission_trace", "canonical_filename": "submission_trace.json", "type": "json"},
                ],
                "schemas": {
                    "spectrum.json": {"required_fields": ["bin_edges", "signal_counts"]},
                    "submission_trace.json": {"required_fields": ["workflow_stages"]},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    write_json(
        submission_dir / "spectrum.json",
        {
            "bin_edges": [80.0, 120.0, 130.0, 145.0, 155.0, 250.0],
            "signal_counts": [1.0, 2.0, 4.0, 50.0, 3.0],
        },
    )
    write_json(
        submission_dir / "submission_trace.json",
        {
            "workflow_stages": [
                {
                    "stage_id": "manifest_sample_survey",
                    "description": "Read manifest files and sample roles before choosing a strategy.",
                },
                {
                    "stage_id": "lepton_candidate_strategy",
                    "description": "Apply defensible lepton quality and isolation selection while building candidates.",
                },
                {
                    "stage_id": "m4l_spectrum_and_window_scan",
                    "description": "Reconstruct the invariant mass observable, bin the spectrum, and compare windows.",
                },
                {
                    "stage_id": "robustness_and_conclusion",
                    "description": "Run validation checks and report an evidence-bound interpretation.",
                },
            ],
            "scientific_decisions": [
                {
                    "decision": "Use a wider signal scan than L1.",
                    "reason": "L3 permits open strategy if evidence is auditable.",
                    "impact_on_analysis": "The localized excess claim depends on the observed spectrum peak.",
                }
            ],
        },
    )
    rubric = {
        "version": 1,
        "weights": {"pipeline": 1.0, "analysis": 1.0},
        "checks": {
            "pipeline": [
                {
                    "id": "open_strategy_functions",
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
                                "validation",
                            ],
                            "minimum_pass_fraction": 0.7,
                            "partial_credit": False,
                        }
                    },
                    "score": 1.0,
                }
            ],
            "analysis": [
                {
                    "id": "peak_near_125",
                    "type": "deterministic",
                    "condition": {
                        "histogram_peak_location": {
                            "file": "spectrum.json",
                            "primary_series": "signal_counts",
                            "expected_range": [120.0, 130.0],
                        }
                    },
                    "score": 1.0,
                }
            ],
        },
    }
    task = SimpleNamespace(
        id="generic_l3",
        type="hzz4l_l3",
        level="l3",
        spec_dir=str(task_dir),
        submission_contract_path="submission_contract.yaml",
    )

    report = score_submission(task, submission_dir, rubric, {"status": "ok", "hard_checks_passed": True})
    checks = {check["id"]: check for check in report["check_results"]}

    assert checks["open_strategy_functions"]["passed"]
    assert not checks["peak_near_125"]["passed"]
