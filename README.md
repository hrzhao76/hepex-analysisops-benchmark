# HEPEx AnalysisOps Benchmark

A benchmark for evaluating autonomous research agents on realistic high-energy physics (HEP) analysis workflows, including data processing, statistical fitting, and result validation.

## Abstract
This benchmark evaluates an autonomous agent's ability to perform end-to-end physics analyses using ATLAS Open Data. The Green Agent currently supports **seven** tasks:

1.  **Z Boson Resonance Fit (`zpeak_fit`)**: Extract Z mass and width from muon pairs.
2.  **Higgs to Diphoton Analysis (`hyy`)**: Measure Higgs mass using high-resolution diphoton events.
3.  **H->mumu (VBF) (`hmumu`)**: Search for the rare Higgs decay to muons using VBF topology selection.
4.  **H->bb (0-lepton) (`hbb`)**: Identify Higgs to b-quark pairs in the high-MET VH channel.
5.  **H->ZZ->4l (`hzz`)**: Rediscover the "Golden Channel" Higgs decay to four leptons.
6.  **Top Pair Production (`ttbar`)**: Reconstruct the top quark mass in the semileptonic decay channel.
7.  **WZ Diboson (`wz3l`)**: Analyze WZ production in the 3-lepton final state.

The benchmark focuses on "AnalysisOps"—the structured, repetitive, yet critical operations of maintaining analysis code, running fits, and validating results—rather than purely novel algorithm design.

## Features
*   **Green Agent Implementation**: Fully compliant with the [Agent2Agent (A2A) Protocol](https://a2a-protocol.org), serving as an orchestrator and evaluator.
*   **Realistic Physics Tasks**: Uses real ATLAS Open Data (13 TeV) and standard ROOT/Python ecosystems (uproot, iminuit).
*   **Deterministic Evaluation**: The evaluation engine uses strict, deterministic rule checks defined in YAML rubrics to ensure fair and reproducible scoring.
*   **Mock & White Agent Support**: robust support for developing against mock traces or connecting real "White Agents" via A2A.
*   **Extensible Architecture**: New tasks can be added by defining 5 specification files (TaskSpec, Rubric, EvalRef, WhitePrompt, JudgePrompt).

## Reproducibility
The benchmark prioritizes reproducibility in agent evaluation. The scoring engine is designed to be deterministic for rule-based checks.
*   **Verification**: Multiple runs of the evaluation engine with the same submission trace produce bitwise identical score reports.
*   **Artifacts**: All intermediary inputs (judge input) and outputs (score report) are persisted as JSON artifacts for auditability.
*   **Isolation**: Each task runs in its own isolated directory structure to prevent state leakage.

---

## Architecture

### Roles

- **Green agent (this repo)**  
  Orchestrates tasks, optionally downloads data, collects submissions (mock or from white agent), evaluates them, and reports artifacts.

- **White agent (future / external)**  
  Performs the actual physics analysis and returns a **structured submission trace** (cuts, cutflow, fit metadata, artifacts, etc.).

---

## Data flow

1. AgentBeats sends an `EvalRequest` JSON. 
2. Green Agent (`src/agent.py`) parses request and loads configuration.
3. For each task:
   - **Data Prep**: Caches ATLAS Open Data via `atlasopenmagic`.
   - **Execution**: Sends prompt to White Agent (or uses mock).
   - **Evaluation**: Scores the submission trace against `rubric.yaml` using `src/engine/evaluator.py`.
   - **Reporting**: Updates status and artifacts via A2A.

## Attribution

This benchmark uses **ATLAS Open Data** released under the CERN Open Data policy.
