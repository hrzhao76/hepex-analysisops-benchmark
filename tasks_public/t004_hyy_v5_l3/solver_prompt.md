# Objective

Design and run a scientifically meaningful ATLAS Open Data diphoton analysis that decides whether the provided data contain a localized Higgs-like excess near 125 GeV.

This is an L3 open scientific discovery task. The benchmark defines the goal, input data, and required reporting contract. It does not prescribe the analysis recipe.

# Data

Use ATLAS Open Data:

- Release: `2025e-13tev-beta`
- Dataset: `data`
- Sample or skim: `GamGam`
- Mode: data only

Use the files made visible in the runtime input manifest. A full benchmark run may expose all intended 2015/2016 GamGam periods; a local smoke test may expose only a subset. In either case, analyze the visible manifest scope completely and record the exact files or periods used in `submission_trace.json`.

# Scientific Anchors

Keep these anchors fixed:

- The scientific question is whether there is a localized Higgs-like excess near 125 GeV.
- The main reported result must be based on a diphoton mass spectrum or a clearly justified equivalent diphoton signal proxy.
- The required output artifact filenames and JSON/markdown shapes are defined by the submission contract.
- All numeric claims must come from computation over the provided input files.

# Method Freedom

Choose your own defensible analysis strategy. You may redesign:

- photon and event selection logic,
- photon pairing or ranking strategy,
- supporting observables or cross-checks,
- histogram/binning choices,
- background estimation and signal-localization method,
- robustness checks and validation strategy.

Baseline Hyy cuts, leading/subleading pairing, 1 GeV bins, and Gaussian plus polynomial fits are acceptable references, not mandatory L3 requirements. If you choose a different route, make the mapping to the required artifacts explicit.

# Required Output Files

Return exactly one `submission_bundle_v1` JSON object with these required artifact keys:

- `diphoton_mass_spectrum.json`
- `diphoton_fit_summary.json`
- `data_minus_background.json`
- `interpretation.md`
- `submission_trace.json`

Do not embed binary image data. Optional plots, if used, must be represented by small JSON references only when declared by the contract.

# Trace Requirement

`submission_trace.json` is the L3 strategy and evidence record. It must be structured enough for machine checks and human review.

Include:

- ordered workflow stages with family labels where possible,
- data scope actually used,
- chosen strategy and key scientific decisions,
- observable or signal proxy constructed,
- selection and pairing strategy when applicable,
- inference/background/signal-localization strategy,
- validation or robustness actions,
- result summary,
- generated output filenames.

Useful family labels include `data_access`, `object_or_event_selection`, `observable_construction`, `spectrum_or_summary_construction`, `inference_or_signal_localization`, `residual_or_background_subtraction`, `validation`, and `interpretation`.

# Interpretation

`interpretation.md` should be concise but substantive. Connect method to evidence to conclusion. State whether the visible data support a Higgs-like localized excess, give the approximate location when relevant, and use cautious language when the evidence is limited by statistics or methodology.
