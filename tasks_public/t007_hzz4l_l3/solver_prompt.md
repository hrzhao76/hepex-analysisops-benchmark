# Objective

Design and run a scientifically meaningful ATLAS Open Data analysis of the \(H\to ZZ^*\to 4\ell\) channel. The goal is to decide whether the four-lepton mass spectrum supports a localized Higgs-like excess near 125 GeV when observed data are compared with expected backgrounds and the provided signal sample.

This is an **L3 open scientific discovery** task. The benchmark defines the scientific goal, input scope, and reporting contract. It does not prescribe the analysis recipe.

# Execution Contract

You are executing a real data analysis pipeline, not describing one. All outputs must be derived from actual computation over the provided ROOT files.

Use only ROOT files listed in `input_manifest.json`. Do not download, stream, or open any file or URL outside the manifest. If computation fails because of missing data, schema mismatch, or runtime limitations, return a submission bundle with top-level `status = "error"` and a clear error message. Do not return `status = "ok"` with fabricated, default, or zero-filled artifacts.

# Data Scope

Use the ATLAS Open Data 13 TeV release `2025e-13tev-beta`, dataset `atlas_open_data_13tev`, tree `analysis`, skim `exactly4lep`.

The manifest contains these sample groups:

- **Data**: `data`
- **Background \(Z,t\bar t,t\bar t+V,VVV\)**: `410470`, `410155`, `410218`, `410219`, `412043`, `364243`, `364242`, `364246`, `364248`, `700320`, `700321`, `700322`, `700323`, `700324`, `700325`
- **Background \(ZZ^*\)**: `700600`
- **Signal \((m_H=125\) GeV)**: `345060`, `346228`, `346310`, `346311`, `346312`, `346340`, `346341`, `346342`

Data must remain unweighted. MC backgrounds and signal must be weighted and normalized using available MC normalization information and scale factors, with final normalization corresponding to 36.6 fb\(^{-1}\). Record any missing or inconsistent MC weighting fields and how the limitation affects interpretation.

# Scientific Anchors

Keep these anchors fixed:

- The scientific question is whether there is a localized Higgs-like excess near 125 GeV in \(H\to ZZ^*\to 4\ell\).
- The final reported comparison must include a four-lepton invariant-mass spectrum \(m_{4\ell}\) for data, expected background, signal, and background uncertainty.
- The final conclusion must address the 120-130 GeV region.
- The required output filenames and JSON/markdown shapes are defined by the submission contract.
- All numeric claims must come from computation over manifest files.

# Method Freedom

Choose your own defensible analysis strategy. You may redesign:

- event cleaning and lepton selection logic
- candidate construction or bookkeeping strategy
- supporting observables and cross-checks
- histogram range and binning, if the Higgs region remains covered
- background/signal comparison strategy
- excess-assessment metric or statistical proxy
- validation and robustness approach

Reference-style trigger, trigger matching, lepton quality, isolation, topology, charge, and ordered-\(p_T\) selections are acceptable defaults, not mandatory L3 constraints. If you choose a different route, explain why it remains physically meaningful for a four-lepton Higgs search.

# Required Output Files

Return exactly one `submission_bundle_v1` JSON object with these required artifact keys:

- `four_lepton_mass_spectrum.json`
- `four_lepton_excess_summary.json`
- `interpretation.md`
- `submission_trace.json`

`four_lepton_excess_summary.json` must report the observed yield, background yield, signal yield, numerator yield, significance proxy, and exact significance formula used for the declared signal region. The formula is flexible, but it must be stated and numerically consistent with the spectrum.

# Trace Requirement

`submission_trace.json` is the L3 strategy-and-evidence record. It must be structured enough for machine checks and human review.

Include:

- workflow stages actually executed, with family labels where possible
- execution evidence counters from real computation
- manifest samples and files used
- chosen strategy and key scientific decisions
- observable or signal proxy constructed
- selection or candidate strategy, if applicable
- inference/background/signal-localization strategy
- validation or robustness checks and outcomes
- result summary and generated output filenames

Useful family labels include `data_access`, `object_or_event_selection`, `event_weighting`, `observable_construction`, `spectrum_or_summary_construction`, `inference_or_signal_localization`, `validation`, and `interpretation`.

Include an `execution_evidence` object with these integer fields:

```json
{
  "files_processed_count": 0,
  "events_processed_total": 0,
  "selected_events_total": 0,
  "candidates_built_total": 0,
  "histogram_filled_entries": 0
}
```

Include a `mc_weighting_evidence` object. It is required even if the final strategy uses a fallback weighting mode:

```json
{
  "data_policy": "unweighted",
  "mc_policy": "weighted_and_luminosity_normalized",
  "luminosity_fb_inv": 36.6,
  "weight_formula": "lumi_fb_inv * 1000 * xsec * filteff * kfac * mcWeight * scale_factors / sum_of_weights",
  "event_weight_factors_used": ["mcWeight"],
  "sample_normalization_fields": ["xsec", "filteff", "kfac", "sum_of_weights"],
  "scale_factors_used": ["ScaleFactor_PILEUP", "ScaleFactor_ELE", "ScaleFactor_MUON", "ScaleFactor_LepTRIGGER"],
  "missing_fields": [],
  "fallback_strategy": "none",
  "uncertainty_policy": "background bin uncertainty from sqrt(sum w^2)"
}
```

If any MC weighting field is missing or unusable, list it in `missing_fields`, state the fallback strategy, and make the interpretation reflect the resulting limitation. Do not hide unweighted MC behind a normalized-MC claim.

Record key decisions as structured objects in `scientific_decisions`:

```json
{
  "decision": "...",
  "reason": "...",
  "impact_on_analysis": "..."
}
```

Record validation checks in `validation_checks`. Strong L3 submissions should include checks such as selected-yield sanity, non-empty spectrum, signal-window sanity, sideband or alternative-window checks, binning variation, uncertainty propagation, or data/MC normalization sanity.

# Interpretation

`interpretation.md` should be concise but substantive. Connect method to evidence to conclusion. State whether the visible data support a Higgs-like localized excess, identify the approximate mass location or result region, and use cautious language when evidence is limited by statistics, normalization, or methodology.
