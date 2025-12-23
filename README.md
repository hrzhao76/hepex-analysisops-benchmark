# HEPEx AnalysisOps Benchmark

A benchmark for evaluating autonomous research agents on realistic high-energy physics (HEP) analysis workflows, including data processing, statistical fitting, and result validation. 

## Motivation

A large fraction of day-to-day work in experimental HEP is not novel theory or algorithm design, but structured, repetitive, high-volume analysis operations ("AnalysisOps"): maintaining analysis code, running fits, validating results, generating plots, and updating analysis notes.

This benchmark evaluates whether an autonomous agent can reliably perform such tasks end-to-end under realistic constraints, rather than solving isolated coding puzzles. 

## What Is Being Evaluated

The benchmark evaluates an agent along three dimensions:

1. **Correctness**
   - Numerical agreement with reference results (fit parameters, test statistics)
   - Successful generation of required artifacts (plots, tables, reports)

2. **Operational Robustness**
   - Ability to execute multi-step analysis workflows
   - Graceful handling of minor execution issues (e.g. reruns, missing files)

3. **Efficiency and Quality**
   - Number of steps/tool calls
   - Code clarity and logging
   - Reproducibility of results

## Task Overview

The current MVP task is a simplified ATLAS Open Data analysis workflow:

- Input: a small ATLAS Open Data ROOT / derived dataset
- Goal:
  1. Load the dataset
  2. Perform a predefined statistical fit
  3. Compute test statistics (e.g. best-fit value, uncertainty, p-value)
  4. Generate a standard analysis plot
- Output:
  - `fit_results.json`
  - `fit_plot.png`

## Dataset

This benchmark uses publicly available datasets from **[ATLAS Open Data](https://opendata.cern.ch)**.

To ensure fast evaluation and reproducibility, we:
- use a small, preselected subset of the data
- provide derived inputs where appropriate
- avoid detector-specific private calibrations

The goal is not physics discovery, but realistic analysis workflows.

## AgentBeats Phase

This repository implements the Phase-1 benchmark and green agent for the [AgentBeats competition](https://agentbeats.dev/).

Purple agents can be evaluated by submitting their outputs to the assessor interface defined here.

## Attribution

This benchmark uses ATLAS Open Data released under the CERN Open Data policy.

