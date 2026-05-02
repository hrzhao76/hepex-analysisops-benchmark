# 1. Objective

Perform an L1 diphoton analysis by reconstructing the diphoton invariant-mass spectrum (m_γγ) and testing for a localized Higgs-like excess near 125 GeV.

Do not assume the excess must be observed. The correct answer may be a limited-statistics or inconclusive result if the runtime gives only a small input subset.

---

# 2. Dataset

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

# 3. Submission Contract Requirement

Before producing any outputs, you MUST read the submission contract carefully.

The submission contract is the authoritative specification for:
- required filenames
- required fields
- field naming
- output completeness

Do NOT invent alternative output formats.

This prompt defines scientific behavior only.

---

# 4. Required Workflow (Strict L1 Execution)

Reproduce the baseline workflow exactly in this order:

1. data_loading  
2. event_selection  
3. diphoton_mass_construction  
4. spectrum_histogramming  
5. uncertainty_assignment  
6. spectrum_fitting  
7. signal_interpretation  

Do NOT reorder, skip, or redesign stages.

In `submission_trace.json`, encode these stages exactly as objects with
`stage_id`, `order_index`, `status`, and `depends_on`:

```json
[
  {"stage_id": "data_loading", "order_index": 1, "status": "ok", "depends_on": []},
  {"stage_id": "event_selection", "order_index": 2, "status": "ok", "depends_on": ["data_loading"]},
  {"stage_id": "diphoton_mass_construction", "order_index": 3, "status": "ok", "depends_on": ["event_selection"]},
  {"stage_id": "spectrum_histogramming", "order_index": 4, "status": "ok", "depends_on": ["diphoton_mass_construction"]},
  {"stage_id": "uncertainty_assignment", "order_index": 5, "status": "ok", "depends_on": ["spectrum_histogramming"]},
  {"stage_id": "spectrum_fitting", "order_index": 6, "status": "ok", "depends_on": ["uncertainty_assignment"]},
  {"stage_id": "signal_interpretation", "order_index": 7, "status": "ok", "depends_on": ["spectrum_fitting"]}
]
```

---

# 5. Event/Object Selection (Exact Baseline)

Use the leading and subleading photons.

Baseline assumption:
- photon indices 0 and 1 correspond to the ordered leading/subleading pair in this dataset

Do NOT search for alternative pairings.

Apply ALL cuts exactly:

- photon_count >= 2
- leading photon tight ID == true
- subleading photon tight ID == true
- leading photon pt > 50 GeV, using the branch value directly
- subleading photon pt > 30 GeV, using the branch value directly
- isolation ratio < 0.055
- eta transition veto [1.37, 1.52]
- m_yy != 0
- pt / m_yy > 0.35 (both photons)

Do NOT modify thresholds or logic.

Important numerical safety requirement:
- Compute `m_yy` first.
- Construct `m_yy` from the same unscaled branch units used for `photon_pt` and
  `photon_e`; do not mix scaled and unscaled quantities.
- Apply an explicit finite, nonzero mass mask (`m_yy > 0` and finite) before
  calculating any `photon_pt / m_yy` ratio.
- Do not divide by zero and do not keep events with non-finite ratios.
- If a realistic GamGam subset yields zero selected events after all cuts,
  inspect unit handling before returning the final bundle.

In `submission_trace.json`, encode the object definition exactly as:

```json
{
  "type": "photon_pair",
  "multiplicity": 2,
  "ordering_principle": "leading_subleading_photon_pair",
  "baseline_assumption": {
    "leading_photon_index": 0,
    "subleading_photon_index": 1
  }
}
```

Encode `cuts_applied` with these exact `cut_id` values and fields:

```json
[
  {"cut_id": "at_least_two_photons", "applies_to": "event", "variable": "photon_count", "operator": ">=", "value": 2, "applied": true},
  {"cut_id": "leading_photon_tight_id", "applies_to": "leading_photon", "variable": "photon_isTightID", "operator": "==", "value": true, "applied": true},
  {"cut_id": "subleading_photon_tight_id", "applies_to": "subleading_photon", "variable": "photon_isTightID", "operator": "==", "value": true, "applied": true},
  {"cut_id": "leading_photon_pt", "applies_to": "leading_photon", "variable": "photon_pt", "operator": ">", "value": 50.0, "applied": true},
  {"cut_id": "subleading_photon_pt", "applies_to": "subleading_photon", "variable": "photon_pt", "operator": ">", "value": 30.0, "applied": true},
  {"cut_id": "leading_photon_isolation", "applies_to": "leading_photon", "variable": "photon_ptcone20", "operator": "<", "value": 0.055, "depends_on": ["photon_ptcone20", "photon_pt"], "applied": true},
  {"cut_id": "subleading_photon_isolation", "applies_to": "subleading_photon", "variable": "photon_ptcone20", "operator": "<", "value": 0.055, "depends_on": ["photon_ptcone20", "photon_pt"], "applied": true},
  {"cut_id": "leading_photon_eta_transition_veto", "applies_to": "leading_photon", "variable": "abs_photon_eta", "operator": "interval_veto", "interval": [1.37, 1.52], "applied": true},
  {"cut_id": "subleading_photon_eta_transition_veto", "applies_to": "subleading_photon", "variable": "abs_photon_eta", "operator": "interval_veto", "interval": [1.37, 1.52], "applied": true},
  {"cut_id": "diphoton_mass_nonzero", "applies_to": "diphoton_pair", "variable": "m_yy", "operator": "!=", "value": 0.0, "applied": true},
  {"cut_id": "leading_photon_pt_over_m_yy", "applies_to": "leading_photon", "variable": "photon_pt_over_m_yy", "operator": ">", "value": 0.35, "applied": true},
  {"cut_id": "subleading_photon_pt_over_m_yy", "applies_to": "subleading_photon", "variable": "photon_pt_over_m_yy", "operator": ">", "value": 0.35, "applied": true}
]
```

---

# 6. Observable and Histogram

Primary observable: m_yy

- range: 100–160 GeV
- bin width: 1 GeV
- uncertainty: sqrt(N)

In `submission_trace.json`, encode derived observables and histogram metadata exactly as:

```json
{
  "derived_observables": [
    {"name": "abs_photon_eta", "depends_on": ["photon_eta"]},
    {"name": "m_yy", "depends_on": ["photon_pt", "photon_eta", "photon_phi", "photon_e"]},
    {"name": "photon_pt_over_m_yy", "depends_on": ["photon_pt", "m_yy"]}
  ],
  "primary_observable": {
    "name": "m_yy",
    "inputs": ["photon_pt", "photon_eta", "photon_phi", "photon_e"],
    "construction": "invariant_mass_of_first_two_photon_four_vectors"
  },
  "histogram_definition": {
    "observable": "m_yy",
    "range": [100.0, 160.0],
    "bin_width": 1.0,
    "uncertainty_model": "sqrt_n_statistical_uncertainty"
  }
}
```

---

# 7. Inference (Strict Baseline)

Attempt the baseline fit with:

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

In `submission_trace.json`, encode the fit metadata exactly as:

```json
{
  "signal": "gaussian",
  "background": "polynomial",
  "background_order": 4,
  "fit_range_GeV": [100.0, 160.0],
  "weighting_scheme": "inverse_sqrt_bin_count"
}
```

---

# 8. Required Outputs

- diphoton_mass_spectrum.json
- diphoton_fit_summary.json
- data_minus_background.json
- interpretation.md
- submission_trace.json

---

# 9. Execution Trace Requirement (CRITICAL)

submission_trace.json is REQUIRED.

It must be STRUCTURED (not narrative).

It must include:

- workflow_stages (ordered execution)
- cuts_applied (with explicit values)
- observable_constructed
- fit_model_family_used
- output_files_generated
- reported_result (including signal_peak_position)
- input_files_used (array of exact input file paths used)
- input_file_count (integer, exactly `len(input_files_used)`)
- selected_events_total (integer selected event count after all baseline cuts)
- cutflow_summary with at least `input_events` and `selected_events`

Do NOT use free-form text as the main structure.

Every trace claim must be consistent with the actual artifacts:

- `reported_result.signal_peak_position` must match `diphoton_fit_summary.json.signal_peak_position`
- `output_files_generated` must list exactly the five required filenames
- `input_file_count` must match the number of entries in `input_files_used`
- `selected_events_total` must match `cutflow_summary.selected_events`
- `diphoton_mass_spectrum.json.bin_edges` must have length `len(bin_counts) + 1`
- `bin_counts` and `bin_uncertainties` must have the same length
- `data_minus_background.json.bin_centers`, `residual_counts`, and `residual_uncertainties` must have the same length

---

# 10. Anti-Cheating Requirement

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

# 11. Interpretation Requirement

Write a short conclusion:

- whether the analyzed subset supports, does not support, or is inconclusive for a Higgs-like excess
- approximate peak position only if the fit is meaningful

The conclusion must be consistent with the fit and residual results.
For `max_files=1` or any partial manifest, use limited-statistics language and
do not claim a full ATLAS-period rediscovery.

---

# 12. Runtime Input Rules

If `request.data.work_dir` or `request.data.output_dir` is provided, use that
directory as the analysis working directory for generated scripts, logs, plots,
and intermediate files. Do not write task outputs into `$HOME/output` directly
unless no working directory is provided.

If `shared_input_dir` is provided, treat it as read-only input.
Do not modify dataset files in place.
Return outputs through `submission_bundle_v1` as small structured artifacts only.

If `input_manifest_path` is provided, read it first and use only the ROOT files listed there.
If no shared input manifest is provided, use the data access information in the request, but still produce the same submission bundle contract.
