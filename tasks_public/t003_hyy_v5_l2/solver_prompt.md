# 1. Objective

Reconstruct a diphoton invariant-mass analysis from ATLAS Open Data and decide whether the selected spectrum contains a localized Higgs-like excess near 125 GeV.

This is an L2 guided-autonomy task. The benchmark is testing whether you can reconstruct a scientifically valid workflow from the objective, data, and output contract. It is not asking you to copy a fixed L1 recipe.

# 2. Dataset

Use ATLAS Open Data:

- Release: `2025e-13tev-beta`
- Dataset: `data`
- Sample or skim: `GamGam`
- Mode: data only

Use the files made visible in the runtime input manifest. If the manifest lists a subset of periods for a local smoke test, analyze that listed subset completely and record the exact file/period coverage in `submission_trace.json`.

# 3. Hard Scientific Constraints

These constraints define the task identity and must be preserved:

- The physics goal is a diphoton search for a Higgs-like localized excess near 125 GeV.
- The primary observable is the diphoton invariant mass, usually named `m_yy`, `m_gg`, or `diphoton_invariant_mass`.
- The observable must be constructed from two selected photons using the available four-vector inputs, such as `photon_pt`, `photon_eta`, `photon_phi`, and `photon_e`.
- Photon selection must use defensible photon quality, kinematic, isolation, and detector-region information when those branches are available.
- Produce the required artifacts with the canonical filenames in the submission contract.
- All reported numbers and conclusions must be derived from computation over the provided input files.

# 4. Flexible Components

The baseline Hyy analysis is a reference, not a prescription. You may choose scientifically reasonable alternatives for:

- workflow stage structure and ordering, as long as data access, selection, observable construction, spectrum construction, inference, and interpretation are all evidenced
- exact photon thresholds and cut ordering
- handling events with more than two photons
- diphoton pairing strategy
- histogram range and bin width, provided the spectrum covers the Higgs signal region and enough sideband to support a background estimate
- fitting or signal-localization method
- optimizer, numerical library, and uncertainty treatment
- diagnostic checks and plots

Reference choices such as a 100 to 160 GeV mass window, 1 GeV binning, leading/subleading photon pairing, and a Gaussian plus smooth-polynomial background fit are acceptable defaults. They are not mandatory L2 constraints. If you choose a different reasonable strategy, document the choice and why it remains scientifically valid.

# 5. Expected Analysis Evidence

Your workflow should provide structured evidence that it:

- loaded the manifest files and combined the visible data scope
- selected photon candidates with quality, kinematic, isolation, and detector-region reasoning where possible
- constructed a two-photon invariant-mass observable
- built a binned spectrum or equivalent mass summary around the 125 GeV signal region
- estimated a smooth background and localized signal behavior, or used an equivalent signal-localization method
- produced a residual, background-subtracted, or equivalent data-minus-background diagnostic
- interpreted the result consistently with the spectrum and residual/fit evidence

# 6. Required Output Files

Return exactly one `submission_bundle_v1` JSON object. Its artifact keys must match the required canonical filenames from the contract:

- `diphoton_mass_spectrum.json`
- `diphoton_fit_summary.json`
- `data_minus_background.json`
- `interpretation.md`
- `submission_trace.json`

Do not invent alternative required artifact names. Optional artifacts may be omitted unless the contract declares them and you can provide them as small JSON references.

# 7. Contract-Specific Notes

The submission contract is authoritative for field names and JSON shapes. In particular:

- `diphoton_fit_summary.json` should use the generic field `signal_peak_gev` for the best localized signal position, even if your method is not a Gaussian fit.
- `method_family`, `signal_model_family`, and `background_model_family` should describe your actual inference method, not a baseline method you did not use.
- `data_minus_background.json` may contain residuals from a fit background, sideband interpolation, or another clearly described background estimate.
- JSON artifacts must be JSON objects. `interpretation.md` must be a markdown string.

# 8. Execution Trace Requirement

`submission_trace.json` is mandatory. It is the L2 decision and execution record, not a prose appendix.

Include structured fields that show:

- `workflow_stages`: ordered stage objects with `stage_label`, `family`, and `status`
- `data_scope`: release, dataset/sample, input files or periods used, and whether the listed files were combined
- `scientific_decisions`: a concise list of key choices, especially deviations from baseline defaults
- `selection_strategy`: photon selection and pairing strategy, including explicit detector-region handling such as eta acceptance, transition-region veto, or calorimeter-crack exclusion when used
- `observable_constructed`: observable name, inputs, and construction method
- `inference_strategy`: method family, signal model or proxy, background model or estimate, fit/localization range, and uncertainty treatment
- `output_files_generated`: the required artifact filenames actually produced

Use clear family labels when possible: `data_access`, `object_or_event_selection`, `observable_construction`, `spectrum_or_summary_construction`, `inference_or_signal_localization`, `residual_or_background_subtraction`, `interpretation`, and `validation`.

# 9. Interpretation Requirement

`interpretation.md` should be concise. State whether a localized Higgs-like excess is observed, give the approximate location when appropriate, and connect the claim to the spectrum and residual/fit evidence. Briefly justify major analysis choices that differ from baseline defaults.

# 10. Runtime Rules

If `shared_input_dir` or `input_manifest_path` is provided, treat the input data as read-only. Put any temporary scripts or intermediate files under the provided solver work directory when available. Return only small structured artifacts in `submission_bundle_v1`; do not embed binary image data.
