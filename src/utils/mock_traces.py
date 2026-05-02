from __future__ import annotations

from typing import Any


def mock_bundle_zpeak_fit(task_id: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "artifacts": {
            "fit_summary.json": {
                "task_id": task_id,
                "status": "ok",
                "fit_result": {
                    "mu": 91.3,
                    "sigma": 2.5,
                    "gof": {"p_value": 0.2, "chi2_ndof": 1.1},
                },
                "fit_method": {
                    "model": "Gaussian plus linear background",
                    "fit_range": [70.0, 110.0],
                    "binned_or_unbinned": "binned",
                    "optimizer": "scipy.curve_fit",
                    "initial_params": {"mu": 91.2, "sigma": 2.4},
                    "uncertainties_method": "covariance",
                },
                "comments": "Mock Z peak fit result for public contract validation.",
            },
            "interpretation.md": "The mock di-muon spectrum has a Z-like peak near 91.3 GeV with a finite fitted width.",
            "submission_trace.json": {
                "task_id": task_id,
                "status": "ok",
                "workflow_stages": [
                    {"stage_id": "data_loading", "order_index": 1, "status": "ok"},
                    {"stage_id": "muon_pair_selection", "order_index": 2, "status": "ok"},
                    {"stage_id": "mass_spectrum", "order_index": 3, "status": "ok"},
                    {"stage_id": "z_peak_fit", "order_index": 4, "status": "ok"},
                ],
                "output_files_generated": [
                    "fit_summary.json",
                    "interpretation.md",
                    "submission_trace.json",
                ],
            },
        },
    }


def mock_bundle_hyy_l1(task_id: str) -> dict[str, Any]:
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
                "task_id": task_id,
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


MOCK_BUNDLE_REGISTRY = {
    "zpeak_fit": mock_bundle_zpeak_fit,
    "hyy_l1": mock_bundle_hyy_l1,
}


def get_mock_bundle(task_type: str, task_id: str) -> dict[str, Any]:
    handler = MOCK_BUNDLE_REGISTRY.get(task_type)
    if handler:
        return handler(task_id)
    return {
        "status": "error",
        "error": f"Unknown mock submission bundle task type: {task_type}",
        "artifacts": {},
    }
