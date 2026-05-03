# Objective

Rediscover the Higgs boson in the \(H\to ZZ^*\to 4\ell\) channel by reconstructing the four-lepton invariant-mass spectrum \(m_{4\ell}\) and comparing observed data to expected backgrounds. The core scientific conclusion is whether the spectrum shows a localized excess near 125 GeV consistent with Higgs production.

# Dataset

Use the ATLAS Open Data 13 TeV release `2025e-13tev-beta`, dataset `atlas_open_data_13tev`, tree `analysis`, skim `exactly4lep`.

Use only the ROOT files listed in the provided `input_manifest.json`. Do not download, stream, or open any ROOT file or URL that is not listed in the manifest. If the manifest is a capped smoke subset, analyze that subset and state the limited sample coverage in `submission_trace.json` and `interpretation.md`.

Use only these samples:

- **Data**: `data`
- **Background \(Z,t\bar t,t\bar t+V,VVV\)**: `410470`, `410155`, `410218`, `410219`, `412043`, `364243`, `364242`, `364246`, `364248`, `700320`, `700321`, `700322`, `700323`, `700324`, `700325`
- **Background \(ZZ^*\)**: `700600`
- **Signal (\(m_H=125\) GeV)**: `345060`, `346228`, `346310`, `346311`, `346312`, `346340`, `346341`, `346342`

Concatenate files within each sample. Keep data unweighted. Compare data to weighted stacked MC backgrounds with a weighted signal overlay normalized to 36.6 fb\(^{-1}\).

# Scientific Constraints

## Non-Negotiable Scientific Constraints

- The analysis must remain a **four-lepton Higgs signal search** in the \(H\to ZZ^*\to 4\ell\) final state using the dataset and sample scope above.
- The primary observable is the **four-lepton invariant mass** \(m_{4\ell}\), constructed from the **first four leptons** using `lep_pt`, `lep_eta`, `lep_phi`, and `lep_e`.
- The analysis must preserve the identity of a **clean four-lepton candidate selection** suitable for the \(4e\), \(2e2\mu\), or \(4\mu\) topology, with overall charge consistent with zero and trigger-compatible event selection.
- Data must remain unweighted. MC backgrounds and signal must be weighted and normalized using the provided MC normalization information and scale factors, with final normalization corresponding to **36.6 fb\(^{-1}\)**.
- The main spectrum output must be a binned \(m_{4\ell}\) comparison over **80 to 250 GeV** containing data, total background, signal overlay, and MC statistical uncertainty.
- The scientific conclusion must explicitly address whether there is a **localized excess near 125 GeV**, with the relevant signal region centered on the Higgs mass and interpreted within the broader **120–130 GeV** region.
- The excess summary must use a **counting-style assessment** based on a peak-region window near the Higgs mass, reporting the implemented signal region, background yield, numerator yield after signal inclusion, and the significance proxy.
- Use stacked MC backgrounds as the background expectation and the provided Higgs MC sample as the signal template/overlay.

# Flexible Components

The baseline approach is a **reference, not a prescription**, except for the scientific constraints above.

You may choose and justify your own scientifically valid implementation of the analysis, including reasonable variation in:

- exact workflow structure and stage ordering
- cut ordering
- event-selection implementation details
- histogram implementation details
- binning choices within reasonable bounds for the required spectrum
- pairing or bookkeeping strategy, if needed
- coding framework and numerical implementation
- equivalent counting-style realization of the excess assessment

Reference-style guidance includes using trigger and trigger-matching requirements, ordered-lepton \(p_T\) thresholds, flavour-dependent lepton ID/isolation, flavour-topology consistency, total charge zero, first-four-lepton construction from the `exactly4lep` skim, and a peak-window assessment around 125 GeV. You may adapt such components if the resulting workflow remains scientifically faithful to the task and you document the changes clearly.

# Workflow Freedom

Reconstruct a scientifically valid end-to-end workflow rather than copying a fixed recipe.

Your workflow should cover the necessary analysis functions, including sample assembly, event selection, observable construction, MC weighting, spectrum construction, and excess assessment, but you may organize these steps differently if justified.

Document any meaningful deviation from the baseline reference, especially if it affects selection strategy, observable construction details, binning, weighting, or excess-assessment implementation.

# Required Output Files

- `four_lepton_mass_spectrum.json`
- `four_lepton_excess_summary.json`
- `interpretation.md`
- `submission_trace.json`

# Execution Trace Requirement

`submission_trace.json` is mandatory and serves as the L2 decision and execution trace.

It must provide structured evidence for:

- the workflow stages actually executed
- the manifest samples and files used, recorded in `input_samples_used`
- the selection strategy or cuts applied
- key analysis decisions and any meaningful deviations from the baseline reference
- the observable that was constructed
- the model family or inference strategy used
- the generated outputs

Record the manifest samples used in a machine-readable way. Include the four sample names exactly:

- `Data`
- `Background $Z,t\bar{t},t\bar{t}+V,VVV$`
- `Background $ZZ^{*}$`
- `Signal ($m_H$ = 125 GeV)`

Use the `input_samples_used` field in `submission_trace.json`. Each entry must include `sample_name`, `sample_role`, and `files_used`. If you record file paths or URLs, every ROOT reference must match an entry in `input_manifest.json`.

# Submission Contract Awareness

All required outputs must follow the provided submission contract exactly.

The submission contract defines file structure and field names. This prompt defines the scientific behavior and required analysis content, not the output schema.

# Interpretation Requirement

Provide a brief scientific conclusion with brief reasoning.

It must:

- state whether the expected excess or signal-like pattern was observed
- identify the approximate peak or result location when appropriate
- briefly justify major analysis choices if they differ from the baseline reference

Do **not** write a long essay or tutorial-style explanation.
