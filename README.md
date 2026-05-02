# HEPEx AnalysisOps Benchmark

[![Test and Publish Agent](https://github.com/hrzhao76/hepex-analysisops-benchmark/actions/workflows/test-and-publish.yml/badge.svg)](https://github.com/hrzhao76/hepex-analysisops-benchmark/actions/workflows/test-and-publish.yml)

The HEPEx AnalysisOps Benchmark is the AgentBeats Green Agent for evaluating
autonomous agents on reproducible high-energy physics analysis workflows.

The current public surface is intentionally narrow:

- Public task source: `tasks_public/*`
- Solver response format: `submission_bundle_v1`
- Public task contract: `submission_contract.yaml`
- Scoring input: materialized task run directory
- Public scoring: locally reproducible contract and artifact checks
- Hidden scoring: private rubric supplied through `GREEN_SECRETS_JSON`

Legacy `specs/*` task definitions and direct trace submission paths are no
longer part of the public interface.

## Repository Role

This repository owns the Green Agent:

1. Parse an AgentBeats `EvalRequest`.
2. Load public task specs from `tasks_public`.
3. Prepare runtime inputs and per-task run directories.
4. Send a task payload to a Purple Agent over A2A.
5. Materialize the returned `submission_bundle_v1`.
6. Validate the public directory contract.
7. Apply optional hidden rubric scoring.
8. Emit one machine-readable task report per task.

Transport lives in `src/agent.py`. Benchmark execution lives in
`src/engine/benchmark_engine.py`. Submission evaluation lives in
`src/engine/evaluation.py`.

## Task Maturity Matrix

| Task | Public contract ready | Private rubric ready | Leaderboard live | Quick-submit ready | Tests passing | Notes |
|------|-----------------------|----------------------|------------------|--------------------|---------------|-------|
| `tasks_public/t001_zpeak_fit` | yes | no | no | yes | yes | Minimal Z peak public-contract task. |
| `tasks_public/t002_hyy_v5_l1` | yes | yes | yes | yes | yes | Hyy L1 diphoton analysis with public contract plus hidden L1 rubric. |

Every public task directory must contain:

```text
task_spec.yaml
solver_prompt.md
submission_contract.yaml
```

## Public Submission Contract

Purple Agents return exactly one JSON object:

```json
{
  "status": "ok",
  "artifacts": {
    "canonical_filename.json": {},
    "canonical_filename.md": "markdown text"
  }
}
```

Artifact keys must match `submission_contract.yaml` exactly. The Green Agent
materializes each artifact into the task run directory and then validates the
directory contract. `submission_trace.json` is just one bundle artifact; it is
not a separate public response mode.

For `t002_hyy_v5_l1`, `submission_trace.json` must include explicit provenance
fields:

- `input_files_used`
- `input_file_count`
- `selected_events_total`
- `cutflow_summary.input_events`
- `cutflow_summary.selected_events`

These fields make local debugging and leaderboard queries deterministic.

## Development Setup

Prerequisites:

- Python managed through `uv`
- Docker, for image and compose testing
- An OpenAI API key if running hidden LLM rubric checks

Install and test:

```bash
uv sync
uv run pytest -q
```

Run the Green Agent locally:

```bash
uv run src/server.py --host 0.0.0.0 --port 9009
```

Build the local Docker image:

```bash
docker build -t hepex-green-agent:local .
```

## Downloading Shared Input Data

For a realistic local E2E run, download the ATLAS Open Data ROOT files into the
benchmark shared input tree:

```bash
uv run python scripts/download_root_files.py \
  --skim GamGam \
  --max-files -1 \
  --json-output ./shared_input/download_manifest.json
```

By default the files are written to:

```text
shared_input/2025e-13tev-beta/data/GamGam/
```

`--max-files -1` means no local cap. The JSON file is a downloader manifest for
local audit; the benchmark run manifest is prepared by the Green Agent when the
local shared-data workflow starts.

## EvalRequest

Minimal request:

```json
{
  "participants": {
    "purple_agent": "http://purple-agent:9009/"
  },
  "config": {
    "task_dirs": ["tasks_public/t002_hyy_v5_l1"],
    "data_dir": "/home/agent/output"
  }
}
```

Full local shared-data request:

```json
{
  "participants": {
    "purple_agent": "http://purple-agent:9009/"
  },
  "solver_backend": "agent_1_oh",
  "config": {
    "task_dirs": ["tasks_public/t002_hyy_v5_l1"],
    "data_dir": "/home/agent/output",
    "input_access_mode": "local_shared_mount",
    "shared_input_dir": "/shared/hepex/input/2025e-13tev-beta/data/GamGam",
    "input_manifest_path": "/shared/hepex/input/2025e-13tev-beta/data/GamGam/input_manifest.json",
    "allow_green_download": false,
    "task_overrides": {
      "t002_hyy_v5_l1": {
        "enabled": true,
        "mode": "call_white",
        "input_strategy": "shared_manifest",
        "max_files": 16
      }
    }
  }
}
```

`solver_backend` may be top-level or inside `config`. The default is
`agent_1_oh`, which is the OpenHarness backend implemented by the reference
Purple Agent.

## Scoring Model

Local public scoring is reproducible without private rubric access:

- `public_scores.contract_pass`
- `public_scores.public_structure_score`
- `public_scores.public_artifact_score`

Official leaderboard scoring may include:

- `hidden_scores.hidden_quality_score`
- `score_visibility: official_with_hidden`

If no matching private rubric is available, a public-contract-passing task
returns an explainable public-only score instead of silently collapsing to zero.

## Private Rubric Secrets

Private rubrics are not stored in `tasks_public`. For local official-like
testing, generate `GREEN_SECRETS_JSON` from the private rubric source:

```bash
uv run python scripts/export_green_secrets.py
```

By default this updates:

- `hepex-analysisops-benchmark/.env`
- `hepex-analysisops-leaderboard/.env`

Run this whenever `submission_contract.yaml` or the private rubric changes,
because the private rubric lookup is keyed by public contract hash.

## Run Artifacts

Each benchmark run writes:

```text
output/
└── runs/<run_id>/
    ├── eval_request.json
    ├── green_config.json
    ├── run_summary.json
    └── <task_id>/
        ├── meta.json
        ├── data_info.json
        ├── purple_request.json
        ├── purple_response_raw.txt
        ├── submission_bundle_raw.json
        ├── artifact_manifest.json
        ├── <materialized artifacts>
        ├── judge_input.json
        └── judge_output.json
```

`run_summary.json` is for local debugging. AgentBeats leaderboard ingestion
uses task result artifacts, not the overall summary object.

## Local End-to-End Workflow

The preferred local full-data path is through the leaderboard wrapper:

```bash
cd ../hepex-analysisops-leaderboard
python3 scripts/local_shared_submit.py \
  --host-input-dir ../hepex-analysisops-benchmark/shared_input/2025e-13tev-beta/data/GamGam \
  --max-files 16 \
  --mode call_white \
  --solver-backend agent_1_oh \
  --build-local-images \
  --no-commit
```

This builds local Green/Purple images, mounts local ROOT files into both
containers, runs Docker Compose, archives `output/results.json` into the
timestamped run directory, and prepares submission artifacts without pushing a
PR when `--no-commit` is set.

## Adding Or Updating A Public Task

1. Create `tasks_public/<task_id>/task_spec.yaml`.
2. Add a solver-facing `solver_prompt.md`.
3. Add `submission_contract.yaml` with `required_outputs` and `schemas`.
4. Add or update mock bundle fixtures in `src/utils/mock_traces.py`.
5. Add public contract tests under `tests/`.
6. Run `uv run pytest -q`.
7. If hidden scoring applies, update the private rubric and rerun
   `scripts/export_green_secrets.py`.

## Useful Commands

```bash
# Unit and integration tests
uv run pytest -q

# Run one test module while iterating
uv run pytest tests/test_hyy_v5_l1_flow.py -q

# Build local Green image
docker build -t hepex-green-agent:local .

# Regenerate GREEN_SECRETS_JSON after rubric or contract changes
uv run python scripts/export_green_secrets.py
```

## Attribution

This benchmark uses ATLAS Open Data released under the CERN Open Data policy.

## License

See `LICENSE`.
