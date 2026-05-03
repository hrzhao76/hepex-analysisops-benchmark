## Objective
- Rediscover the Higgs boson in \(H \to ZZ^* \to 4\ell\) by selecting four-lepton candidate events and examining the four-lepton invariant mass \(m_{4\ell}\) for a localized excess near 125 GeV.

## Dataset
- Source: ATLAS Open Data
- Release: `2025e-13tev-beta`
- Skim: `exactly4lep`
- Mode: `tree=analysis;skim=exactly4lep`
- Use Data, background MC, and signal MC from this release/skim only.
- Use only the ROOT files listed in the provided `input_manifest.json`.
- Do not download, stream, or open any ROOT file or URL that is not listed in `input_manifest.json`.
- The manifest contains these four samples:
  - `Data`
  - `Background $Z,t\bar{t},t\bar{t}+V,VVV$`
  - `Background $ZZ^{*}$`
  - `Signal ($m_H$ = 125 GeV)`
- Years/periods: no additional year or period filtering is specified.
- Combine policy: concatenate selected events across all files within each sample, and compare unweighted Data to weighted stacked MC backgrounds and weighted signal using 36.6 fb\(^{-1}\) for MC normalization.
- If the manifest indicates a capped smoke subset, analyze that subset and state the limited sample coverage in `submission_trace.json` and `interpretation.md`.

## Required Workflow
Execute the baseline workflow faithfully, in exactly this order:

1. `sample_assembly`
   - Assemble Data, background, and signal samples from the specified release and skim.

2. `event_selection`
   - Apply the exact trigger, trigger matching, ordered-lepton \(p_T\), quality, flavor, and charge requirements listed below.

3. `observable_construction`
   - Construct the four-lepton invariant mass from the four selected leptons.

4. `mc_weight_computation`
   - For MC only, compute
     `totalWeight = (36.6 * 1000 / sum_of_weights) * abs(filteff) * abs(kfac) * abs(xsec) * abs(mcWeight) * abs(ScaleFactor_PILEUP) * abs(ScaleFactor_ELE) * abs(ScaleFactor_MUON) * abs(ScaleFactor_LepTRIGGER)`.
   - Keep Data unweighted.

5. `histogramming_and_uncertainties`
   - Fill data and MC mass histograms.
   - Compute per-bin statistical uncertainties exactly as specified.

6. `excess_assessment`
   - Compare the data spectrum to the stacked MC expectation.
   - Evaluate the Higgs-region excess proxy and make a qualitative assessment of a localized excess near 125 GeV.
   - Record at least one validation check tied to the signal region, histogram binning, sidebands, weights, or data-vs-MC consistency.

Do not merge, skip, reorder, redefine, or optimize any step.

## Event/Object Selection
- Use the skimmed four-lepton candidate directly.
- Use the **first four leptons in record order** for the ordered \(p_T\) requirements and for \(m_{4\ell}\) construction.
- Do not re-order, re-pair, or redefine the quartet.

Apply all of the following cuts exactly:

- Event trigger requirement:
  - `event_trigger_pass = (trigE OR trigM)`
  - Require `event_trigger_pass == true`

- Trigger-matched lepton requirement:
  - `trigger_matched_lepton_count = sum(lep_isTrigMatched)`
  - Require `trigger_matched_lepton_count >= 1`

- Ordered lepton \(p_T\) thresholds:
  - `leading_lep_pt = lep_pt[0]` and require `leading_lep_pt > 20.0 GeV`
  - `sub_leading_lep_pt = lep_pt[1]` and require `sub_leading_lep_pt > 15.0 GeV`
  - `third_leading_lep_pt = lep_pt[2]` and require `third_leading_lep_pt > 10.0 GeV`

- Type-dependent lepton quality requirement:
  - `typed_quality_lepton_count = count((lep_type==13 and lep_isMediumID and lep_isLooseIso) or (lep_type==11 and lep_isLooseID and lep_isLooseIso))`
  - Require `typed_quality_lepton_count == 4`

- Four-lepton flavor requirement:
  - `sum_lep_type = lep_type[0] + lep_type[1] + lep_type[2] + lep_type[3]`
  - Require `sum_lep_type` in `{44, 48, 52}` only, corresponding to `4e`, `2e2mu`, or `4mu`

- Total charge requirement:
  - `total_lepton_charge = lep_charge[0] + lep_charge[1] + lep_charge[2] + lep_charge[3]`
  - Require `total_lepton_charge == 0`

Do not loosen, tighten, replace, or supplement these baseline cuts.

## Observable and Histogram
- Primary observable: `mass` / `m_4l`
- Construct it as the invariant mass of the vector sum of the **first four lepton four-vectors** built from:
  - `lep_pt`
  - `lep_eta`
  - `lep_phi`
  - `lep_e`
- Histogram specification:
  - Range: `80.0` to `250.0` GeV
  - Bin width: `2.5` GeV
- Statistical uncertainties:
  - Data: `sqrt(N)`
  - MC: `sqrt(sum_w2)`

## Inference
- Use the model families exactly as follows:
  - Signal model: `histogram_template` using the weighted `m4l` template from Signal MC with `m_H = 125 GeV`
  - Background model: `histogram_template` using weighted stacked `m4l` templates from Background `Z`, `t\bar{t}`, `t\bar{t}+V`, `VVV`, and Background `ZZ*` MC
- Use the fit/inference range exactly: `80.0` to `250.0` GeV
- Weighting must be exactly:
  - Data: unweighted
  - MC: `totalWeight` with full-release luminosity 36.6 fb\(^{-1}\) and the absolute values of `filteff`, `kfac`, `xsec`, `mcWeight`, `ScaleFactor_PILEUP`, `ScaleFactor_ELE`, `ScaleFactor_MUON`, and `ScaleFactor_LepTRIGGER`
- Evaluate the significance proxy in the approximately `122.5` to `130.0` GeV region using the implemented numerator from the total stacked height and denominator `sqrt(N_bg + 0.3 * N_bg^2)`.
- Record at least one validation check in `submission_trace.json` under `validation_checks`.
  - Use `validation_type` equal to one of:
    - `signal_window_sanity_check`
    - `alternative_binning_check`
    - `sideband_check`
    - `data_vs_stacked_mc_consistency_check`
    - `weight_sanity_check`
  - Include a short `result_summary`.
- Produce:
  - the four-lepton mass spectrum
  - the Higgs-region excess summary
  - the qualitative assessment of excess near 125 GeV

## Required Output Files
- `four_lepton_mass_spectrum.json`
- `four_lepton_inference_summary.json`
- `interpretation.md`
- `submission_trace.json`

## Execution Trace Requirement (MANDATORY)
`submission_trace.json` is mandatory and serves as the L1 compliance trace.

The trace must contain sufficient structured information to verify:
- which workflow stages were executed
- which manifest samples and files were used
- which baseline cuts were applied
- which fit model families were used
- which validation checks were performed
- which outputs were generated

Record the manifest samples used in a machine-readable way. Include the four sample names exactly:
- `Data`
- `Background $Z,t\bar{t},t\bar{t}+V,VVV$`
- `Background $ZZ^{*}$`
- `Signal ($m_H$ = 125 GeV)`

Use the `input_samples_used` field in `submission_trace.json`. Each entry must include:
- `sample_name`
- `sample_role`
- `files_used`

If you record file paths or URLs in `submission_trace.json`, every ROOT reference must match an entry in `input_manifest.json`.

For `workflow_stages`, use these exact stage ids when the stage is performed:
- `sample_assembly`
- `event_selection`
- `observable_construction`
- `mc_weight_computation`
- `histogramming_and_uncertainties`
- `excess_assessment`

For `cuts_applied`, use these exact `cut_id` values:
- `event_trigger_requirement`
- `trigger_matched_lepton_requirement`
- `leading_lepton_pt_threshold`
- `subleading_lepton_pt_threshold`
- `third_lepton_pt_threshold`
- `typed_lepton_quality_requirement`
- `four_lepton_flavor_requirement`
- `total_charge_requirement`

For `validation_checks`, include at least one object with:
- `validation_type`
- `status`
- `result_summary`

## Submission Contract Awareness (MANDATORY)
You must produce all required outputs in exact compliance with the provided submission contract.  
The submission contract defines:
- required file structure
- field names
- completeness requirements

If there is any ambiguity between this prompt and the submission contract:
- follow the contract for output format
- follow this prompt for analysis behavior

## Interpretation Requirement
- Write a **SHORT** conclusion in `interpretation.md`.
- It must state:
  - whether a Higgs-like excess is observed
  - the approximate peak location
- Do not include long explanations, design rationales, or optimization commentary.
