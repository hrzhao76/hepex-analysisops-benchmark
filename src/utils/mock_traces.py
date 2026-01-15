from __future__ import annotations
from typing import Any

def mock_trace_zpeak_fit(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "ok",
        "fit_result": {
            "mu": 91.3,
            "sigma": 2.5,
            "gof": {"p_value": 0.2}
        },
        "fit_method": {
            "model": "BreitWigner ⊗ Gaussian + background(poly1)",
            "fit_range": [70, 110],
            "binned_or_unbinned": "binned",
            "optimizer": "iminuit",
            "initial_params": {"mu": 91.2, "sigma": 2.4},
            "uncertainties_method": "HESSE",
            "reasoning": "Standard Z peak fit using Breit-Wigner convolved with Gaussian to account for detector resolution."
        },
        "artifacts": [
            {"id":"fit_result", "kind":"json", "name":"fit_result.json"},
            {"id":"mass_hist", "kind":"histogram", "name":"m_mumu_hist.npz"}
        ]
    }

def mock_trace_hyy(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "ok",
        "fit_result": {
            "center": 125.4,
            "sigma": 2.3,
            "model": "Gaussian + Polynomial4"
        },
        "cuts": [
            {"cut_id":"tight_id","expression":"photon_isTightID"},
            {"cut_id":"pt_abs","expression":"photon_pt > threshold"},
            {"cut_id":"calo_iso","expression":"ptcone20/pt"},
            {"cut_id":"eta_crack_veto","expression":"exclude crack"},
            {"cut_id":"compute_myy","expression":"m_yy"},
            {"cut_id":"pt_rel_myy","expression":"pt/myy"}
        ],
        "cutflow": [
            {"cut_id":"tight_id","n_before":100000,"n_after":20000}
        ],
        # Add basic method/reasoning if hyy spec is updated later to require it
        "fit_method": {
            "model": "Gaussian + Poly4",
            "reasoning": "Classic sideband fit."
        },
        "artifacts": []
    }

def mock_trace_hmumu(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "ok",
        "fit_result": {
            "center": 125.2,
            "sigma": 2.8,
            "significance": 1.5,
            "model": "Signal + Background"
        },
        "fit_method": {
            "model": "Double Gaussian (Signal) + Exponential (Background)",
            "optimizer": "scipy.optimize.curve_fit",
            "fit_range": [110, 160],
            "reasoning": "Using VBF selection to enhance S/B. Vetoing b-jets effectively removes ttbar contamination. The exponential background models the Drell-Yan tail well."
        },
        "cuts": [
            {"cut_id":"trig","expression":"trigM"},
            {"cut_id":"2lep","expression":"lep_n == 2"},
            {"cut_id":"muon_type","expression":"type == 13"},
            {"cut_id":"pt_30","expression":"pt > 30"},
            {"cut_id":"met_80","expression":"met <= 80"},
            {"cut_id":"charge_opp","expression":"charge sum == 0"},
            {"cut_id":"id_iso","expression":"medium ID + loose iso"},
            {"cut_id":"jet_vbf","expression":"vbf cuts (mass>500)"},
            {"cut_id":"bjet_veto","expression":"veto b-jets"}
        ],
        "artifacts": []
    }

def mock_trace_hbb(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "ok",
        "fit_result": {
             "center": 125.0,
             "sigma": 15.0
        },
        "fit_method": {
             "model": "Invariant Mass Calculation",
             "reasoning": "High MET (>150) suppresses QCD. Angular cuts ensure Z boson recoil. 2 b-tags select H->bb."
        },
        "cuts": [
            {"cut_id":"met_trigger","expression":"trigMET"},
            {"cut_id":"met_150","expression":"met > 150"},
            {"cut_id":"zero_lep","expression":"n_lep == 0"},
            {"cut_id":"2_3_jets","expression":"n_jet in [2,3]"},
            {"cut_id":"2_bjets","expression":"n_bjet == 2"},
            {"cut_id":"lead_b_45","expression":"pt_b1 > 45"},
            {"cut_id":"ht_cut","expression":"HT > 120"},
            {"cut_id":"dphi_bb","expression":"dphi < 140"},
            {"cut_id":"dphi_met_bb","expression":"dphi > 120"},
            {"cut_id":"min_dphi_met_jet","expression":"dphi > 20"},
            {"cut_id":"mass_calc","expression":"m(bb)"}
        ],
        "artifacts": []
    }

def mock_trace_hzz(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "ok",
        "fit_result": {
            "center": 124.9,
            "sigma": 1.5,
            "model": "Gaussian"
        },
        "fit_method": {
            "model": "Crystal Ball + Polynomial",
            "reasoning": "Z1 is selected as the pair closest to Z mass. Z2 is the subleading pair. 4-lepton mass shows a clear peak."
        },
        "cuts": [
            {"cut_id":"4lep","expression":"n_lep == 4"},
            {"cut_id":"sfos_pairs","expression":"valid combination"},
            {"cut_id":"z1_mass","expression":"closest to 91.2"},
            {"cut_id":"z2_mass","expression":"12 < m < 115"}
        ],
        "artifacts": []
    }

def mock_trace_ttbar(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "ok",
        "fit_result": {
            "center": 172.5,
            "sigma": 15.0
        },
        "fit_method": {
            "model": "Kinematic Reconstruction",
            "reasoning": "Solved quadratic eq for neutrino Pz using W mass constraint. Used chi2 sorting to resolve jet combinatorics."
        },
        "cuts": [
            {"cut_id":"one_lep","expression":"n_lep == 1"},
            {"cut_id":"met_30","expression":"met > 30"},
            {"cut_id":"w_mt_30","expression":"mt > 30"},
            {"cut_id":"4_jets","expression":"n_jet >= 4"},
            {"cut_id":"2_bjets","expression":"n_bjet >= 2"},
            {"cut_id":"reconstruct_top","expression":"neutrino pz + top mass"}
        ],
        "artifacts": []
    }

def mock_trace_wz3l(task_id: str) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "ok",
        "fit_result": {
            "center": 91.2,
            "sigma": 3.0
        },
        "fit_method": {
            "model": "Z Mass Peak Check",
            "reasoning": "Selected SFOS pair closest to Z mass. Unpaired lepton + MET used for W mT."
        },
        "cuts": [
            {"cut_id":"3lep","expression":"n_lep == 3"},
            {"cut_id":"sfos_z_cand","expression":"sfos pair"},
            {"cut_id":"z_mass_window","expression":"81 < m < 101"},
            {"cut_id":"met_30","expression":"met > 30"},
            {"cut_id":"w_mt_30","expression":"mt > 30"},
            {"cut_id":"reconstruct_w_mass","expression":"w mass"}
        ],
        "artifacts": []
    }

MOCK_REGISTRY = {
    "zpeak_fit": mock_trace_zpeak_fit,
    "hyy_analysis": mock_trace_hyy,
    "hyy": mock_trace_hyy,
    "hmumu": mock_trace_hmumu,
    "hbb": mock_trace_hbb,
    "hzz": mock_trace_hzz,
    "ttbar": mock_trace_ttbar,
    "wz3l": mock_trace_wz3l,
}

def get_mock_trace(task_type: str, task_id: str) -> dict[str, Any]:
    handler = MOCK_REGISTRY.get(task_type)
    if handler:
        return handler(task_id)
    return {"task_id": task_id, "status": "error", "error": f"Unknown task type: {task_type}"}
