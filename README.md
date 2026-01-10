# HEPEx AnalysisOps Benchmark

A benchmark for evaluating autonomous research agents on realistic high-energy physics (HEP) analysis workflows, including data processing, statistical fitting, and result validation. 

## Motivation

A large fraction of day-to-day work in experimental HEP is not novel theory or algorithm design, but structured, repetitive, high-volume analysis operations ("AnalysisOps"): maintaining analysis code, running fits, validating results, generating plots, and updating analysis notes.

This benchmark evaluates whether an autonomous agent can reliably perform such tasks end-to-end under realistic constraints, rather than solving isolated coding puzzles. 

---

## High-level architecture

### Roles

- **Green agent (this repo)**  
  Orchestrates tasks, optionally downloads data, collects submissions (mock or from white agent), evaluates them, and reports artifacts.

- **White agent (future / external)**  
  Performs the actual physics analysis and returns a **structured submission trace** (cuts, cutflow, fit metadata, artifacts, etc.).

---

## Data flow

1. AgentBeats sends an `EvalRequest` JSON to `POST /...` (A2A message endpoint).
2. `src/agent.py` parses the request and loads `GreenConfig`.
3. For each task:
   - Optional: download/cached data via `atlasopenmagic` (`utils/atlas_download.py`)
   - Produce a `submission_trace`:
     - `mock` mode: `utils/mock_traces.py`
     - `call_white` mode: (TODO) call white agent via `Messenger`
   - Run evaluation using `engine/`:
     - load spec package (`workflow.yaml`, `rubric.yaml`, `judge_prompt.md`)
     - rule-based evaluation (v0)
     - aggregate into a final score report
4. Green agent reports progress + artifacts via `TaskUpdater`.

---

## AgentBeats Phase

This repository implements the Phase-1 benchmark and green agent for the [AgentBeats competition](https://agentbeats.dev/).

Purple agents can be evaluated by submitting their outputs to the assessor interface defined here.

## Attribution

This benchmark uses ATLAS Open Data released under the CERN Open Data policy.

