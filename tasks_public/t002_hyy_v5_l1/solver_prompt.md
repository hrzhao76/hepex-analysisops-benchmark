# 1. Objective

Perform an L1 diphoton analysis by reconstructing the diphoton invariant-mass spectrum (m_γγ) and testing for a localized Higgs-like excess near 125 GeV.

Do not assume the excess must be observed. The correct answer may be a limited-statistics or inconclusive result if the runtime gives only a small input subset.

---

# 2. Required Workflow (Strict L1 Execution)

Reproduce the baseline workflow exactly in this order:

1. data_loading  
2. event_selection  
3. diphoton_mass_construction  
4. spectrum_histogramming  
5. uncertainty_assignment  
6. spectrum_fitting  
7. signal_interpretation  

This is a test about if you can strictly and faithfully follow user's instruction, so DO NOT reorder, skip, or redesign stages.

---

# 3. Dataset

Use ATLAS Open Data:

- Release: 2025e-13tev-beta
- Sample: GamGam
- Mode: diphoton_skim

Critical unit convention:
- The benchmark input branches `photon_pt`, `photon_e`, and `photon_ptcone20`
  are already expressed in GeV-scale units for this task.
- Use these branch values directly when applying the 50 GeV / 30 GeV cuts,
  constructing `m_yy`, computing isolation ratios, and filling the 100-160 GeV
  histogram.
- Do NOT divide these branch values by 1000 and do NOT perform a MeV-to-GeV
  conversion unless the runtime data explicitly documents different units.

Use every input file made available by the runtime request. If the request
limits the run with `max_files` or an input manifest subset, analyze that subset
and state the subset honestly in `submission_trace.json`. Only claim that all
2015–2016 periods were combined when the provided input files actually cover
those periods.

---

# 4. Event/Object Selection (Exact Baseline)

Use the leading and subleading photons.

Baseline assumption:
- photon indices 0 and 1 correspond to the ordered leading/subleading pair in this dataset

Do NOT search for alternative pairings.

Apply ALL cuts exactly (cut_id and criteria):

- `at_least_two_photons`: photon_count >= 2
- `leading_photon_tight_id`: leading photon tight ID == true
- `subleading_photon_tight_id`: subleading photon tight ID == true
- `leading_photon_pt`: leading photon pt > 50 GeV
- `subleading_photon_pt`: subleading photon pt > 30 GeV
- `leading_photon_isolation`: leading photon isolation ratio < 0.055
- `subleading_photon_isolation`: subleading photon isolation ratio < 0.055
- `leading_photon_eta_transition_veto`: abs(leading photon eta) not in [1.37, 1.52]
- `subleading_photon_eta_transition_veto`: abs(subleading photon eta) not in [1.37, 1.52]
- `diphoton_mass_nonzero`: m_yy != 0
- `leading_photon_pt_over_m_yy`: pt / m_yy > 0.35
- `subleading_photon_pt_over_m_yy`: pt / m_yy > 0.35

Do NOT modify cut_id, thresholds or logic.

Important numerical safety requirement:
- Compute `m_yy` first.
- Construct `m_yy` from the same unscaled branch units used for `photon_pt` and
  `photon_e`; do not mix scaled and unscaled quantities.
- Apply an explicit finite, nonzero mass mask (`m_yy > 0` and finite) before
  calculating any `photon_pt / m_yy` ratio.
- Do not divide by zero and do not keep events with non-finite ratios.
- If a realistic GamGam subset yields zero selected events after all cuts,
  inspect unit handling before returning the final bundle.

---

# 5. Observable and Histogram

Primary observable: m_yy

- range: 100–160 GeV
- bin width: 1 GeV
- uncertainty: sqrt(N)

---

# 6. Inference (Strict Baseline)

Perform a fit with:

- signal: Gaussian
- background: polynomial (order 4)
- fit range: 100–160 GeV
- use weighting consistent with sqrt(N) uncertainties

Do NOT change model family or configuration.

Only treat the fit as successful if it converges on the histogram produced from
the selected events. If there are too few selected events, the fit is unstable,
or the residuals do not support a localized positive excess near 125 GeV, say so
honestly in `interpretation.md` and `submission_trace.json`. Do NOT fabricate a
peak or force a discovery narrative to satisfy the expected range.

---

# 7. Required Outputs

Your final output will be reveiwed by the benchmark agent program, thus any wrong output format will cause parseing error.
Your final output shold be in JSON format.
DO NOT skip any fields.

Exaxmple template:
{
  "status": "ok",
  "artifacts": {
    "diphoton_mass_spectrum.json": {
      "bin_edges": [...],
      "bin_counts": [...],
      "bin_uncertainties": [...]
    },
    "diphoton_fit_summary.json": {
      "signal_model_family": "...",
      "background_model_family": "...",
      "fit_range": [...],
      "signal_peak_position": ...
    },
    "data_minus_background.json": {
      "bin_centers": [...],
      "residual_counts": [...],
      "residual_uncertainties": [...]
    },
    "interpretation.md": "...",
    "submission_trace.json": {
      "task_id": task_id,
      "workflow_stages": [
        {"stage_id": "data_loading", "order_index": 1, "status": "ok", "depends_on": []},
        ...
      ],
      "baseline_assumptions_used": [
        "...",
      ],
      "object_definition": {
        "type": "...",
        "multiplicity": 2,
        "ordering_principle": "...",
        "baseline_assumption": {
            "leading_photon_index": ...,
            "subleading_photon_index": ...
        }
      },
      "cuts_applied": [
        {"cut_id": "...", "applies_to": "...", "variable": "...", "operator": "...", "value": ..., "applied": True},
        ...
      ],
      "derived_observables": [
        {"name": "...", "depends_on": ["..."]},
        ...
      ],
      "observable_constructed": {
        "name": "...",
        "inputs": ["..."],
        "formula_summary": "..."
      },
      "primary_observable": {
        "name": "...",
        "inputs": ["..."],
        "construction": "..."
      },
      "histogram_definition": {
        "observable": "...",
        "range": [...],
        "bin_width": ...,
        "uncertainty_model": "..."
      },
      "fit_model_family_used": {
        "signal": "...",
        "background": "...",
        "background_order": ...,
        "fit_range_GeV": [...],
        "weighting_scheme": "..."
      },
      "output_files_generated": [
        "...",
      ],
      "reported_result": {
        "signal_peak_position": 125.1
      }
    }
  }
}

---

# 8. Anti-Cheating Requirement

All outputs MUST be derived from actual computation.

Do NOT fabricate results or skip required steps.
Do NOT return placeholder or protocol-validation artifacts.
Do NOT hardcode the final peak position without reading the input ROOT file(s).
Record enough trace information to show which input files, branches, cuts, histogram, and fit settings were used.
Record that energy-like branch values were used directly without a `/1000`
conversion when that is true for the runtime input.

If any stage fails, return `status: "error"` in the bundle with an explanation
rather than returning protocol-valid placeholder artifacts.

---

# 9. Interpretation Requirement

Write a short conclusion:

- whether the analyzed subset supports, does not support, or is inconclusive for a Higgs-like excess
- approximate peak position only if the fit is meaningful

The conclusion must be consistent with the fit and residual results.
For `max_files=1` or any partial manifest, use limited-statistics language and
do not claim a full ATLAS-period rediscovery.


---

# 10. Runtime Input Rules

If `request.data.work_dir` or `request.data.output_dir` is provided, use that
directory as the analysis working directory for generated scripts, logs, plots,
and intermediate files. Do not write task outputs into `$HOME/output` directly
unless no working directory is provided.

If `shared_input_dir` is provided, treat it as read-only input.
Do not modify dataset files in place.
Return outputs through `submission_bundle_v1` as small structured artifacts only.

If `input_manifest_path` is provided, read it first and use only the ROOT files listed there.
If no shared input manifest is provided, use the data access information in the request, but still produce the same submission bundle contract.

