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
        "cuts": [
            {"cut_id":"tight_id","expression":"photon_isTightID[:,0] & photon_isTightID[:,1]"},
            {"cut_id":"pt_abs","expression":"(photon_pt[:,0]>50) & (photon_pt[:,1]>30)"},
            {"cut_id":"calo_iso","expression":"(ptcone20/pt<0.055) for both"},
            {"cut_id":"eta_crack_veto","expression":"exclude |eta| in [1.37,1.52]"},
            {"cut_id":"compute_myy","expression":"(p4[:,0]+p4[:,1]).M"},
            {"cut_id":"pt_rel_myy","expression":"(photon_pt[:,0]/m_yy>0.35) & (photon_pt[:,1]/m_yy>0.35)"}
        ],
        "cutflow": [
            {"cut_id":"tight_id","n_before":100000,"n_after":20000},
            {"cut_id":"pt_abs","n_before":20000,"n_after":12000},
            {"cut_id":"calo_iso","n_before":12000,"n_after":7000},
            {"cut_id":"eta_crack_veto","n_before":7000,"n_after":6500},
            {"cut_id":"compute_myy","n_before":6500,"n_after":6500},
            {"cut_id":"pt_rel_myy","n_before":6500,"n_after":4000}
        ],
        "artifacts": [
            {"id":"submission_trace","kind":"json","name":"submission_trace.json"},
            {"id":"cutflow","kind":"table","name":"cutflow.csv"}
        ]
    }
