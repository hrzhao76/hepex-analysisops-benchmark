# HEPEx AnalysisOps Benchmark

[![Test and Publish Agent](https://github.com/hrzhao76/hepex-analysisops-benchmark/actions/workflows/test-and-publish.yml/badge.svg)](https://github.com/hrzhao76/hepex-analysisops-benchmark/actions/workflows/test-and-publish.yml)

The HEPEx AnalysisOps Benchmark is the AgentBeats Green Agent for reproducible
high-energy physics analysis assessments. In AgentBeats terms, the Green Agent
sets up the task environment, sends public task requests over A2A, validates the
Purple Agent response, applies public and optional hidden scoring, and emits
leaderboard-ready task result JSON.

This repository is built for the AgentX-AgentBeats competition. The public
competition surface is intentionally small and auditable:

- Public task source: `tasks_public/*`
- Solver response format: `submission_bundle_v1`
- Public task contract: `submission_contract.yaml`
- Runtime input evidence: `input_manifest.json`
- Public scoring: local directory-contract and artifact checks
- Hidden scoring: private rubrics supplied through `GREEN_SECRETS_JSON`
- Leaderboard evidence: scenario-driven results in
  `../hepex-analysisops-leaderboard/results/*.json`

AgentBeats describes Green Agents as assessors and Purple Agents as
participants communicating through A2A. The competition judges submissions on
leaderboard performance, generality, cost efficiency, technical quality, and
innovation:

- [AgentBeats platform](https://agentbeats.dev/)
- [AgentBeats tutorial](https://docs.agentbeats.dev/tutorial/)
- [AgentX-AgentBeats competition](https://rdi.berkeley.edu/agentx-agentbeats)

Legacy `specs/*` task definitions and direct trace submission paths are no
longer part of the public interface.

## Repository Role

This repository owns the Green Agent side of HEPEx AnalysisOps:

1. Parse an AgentBeats `EvalRequest`.
2. Load public task packages from `tasks_public`.
3. Prepare task run directories and runtime input manifests.
4. Send a contract-bearing task payload to a Purple Agent over A2A.
5. Materialize the returned `submission_bundle_v1` artifacts.
6. Validate the public submission directory contract.
7. Apply optional private rubric scoring keyed by public contract hash.
8. Emit one machine-readable report per task for leaderboard ingestion.

Transport lives in `src/agent.py`. Benchmark execution lives in
`src/engine/benchmark_engine.py`. Submission evaluation lives in
`src/engine/evaluation.py`.

## Judging Criteria Support

| Competition dimension | Benchmark support |
| --- | --- |
| Leaderboard Performance | Each task report includes `final.normalized_score`, `public_scores`, optional `hidden_scores`, `score_visibility`, `solver_backend`, and six rubric `dimension_scores` when hidden scoring is available. |
| Generality | Public tasks cover Z peak, Hyy diphoton L1/L2/L3, and HZZ4l L1/L2/L3. HZZ4l uses multi-sample manifests across data, background, and signal groups. |
| Cost Efficiency | The Green Agent records `purple_agent_runtime_seconds`, task timing, configured solver backend, solver model, and judge model. It does not currently account for token usage or API-call count directly. |
| Technical Quality | Public schemas, task-package validation, deterministic contract checks, Docker packaging, targeted tests, and persisted run artifacts make failures inspectable. |
| Innovation | The benchmark separates Green/Purple responsibilities, enforces a compact `submission_bundle_v1`, binds private rubrics to public contract hashes, and scores manifest-backed scientific provenance. |

The leaderboard repository contains the competition-facing query layer:

- `../hepex-analysisops-leaderboard/duckdb_queries.json` defines Hyy and HZZ4l
  scoreboard queries over committed `results/*.json`.
- The queries expose task id, level, backend, normalized score, runtime, solver
  model, judge model, hard-check status, and rubric dimension scores.
- Scenario files in `../hepex-analysisops-leaderboard/scenario.toml` and
  `../hepex-analysisops-leaderboard/ci-submit/*.toml` choose the task family,
  solver backend, model, file caps, and shared-input mode.

## Public Tasks

Every public task directory contains:

```text
task_spec.yaml
solver_prompt.md
submission_contract.yaml
task_package_manifest.yaml
```

| Task | Family | Level | Input strategy in task spec | Data shape | Hidden rubric export |
| --- | --- | --- | --- | --- | --- |
| `tasks_public/t001_zpeak_fit` | Z peak dimuon | baseline | `download` | `2025e-13tev-beta/data/2muons`, `max_files=1` | not part of default suite export |
| `tasks_public/t002_hyy_v5_l1` | Hyy diphoton | L1 | `download` by spec, commonly overridden to `shared_manifest` in scenarios | `GamGam`, one-file task default | `--suite hyy` |
| `tasks_public/t003_hyy_v5_l2` | Hyy diphoton | L2 | `shared_manifest` | `GamGam`, `max_files=5` default | `--suite hyy` |
| `tasks_public/t004_hyy_v5_l3` | Hyy diphoton | L3 | `shared_manifest` | `GamGam`, `max_files=5` default | `--suite hyy` |
| `tasks_public/t005_hzz4l_l1` | HZZ4l | L1 | `shared_manifest` | `exactly4lep`, data/background/signal samples, per-sample `max_files=5` default | `--suite hzz` |
| `tasks_public/t006_hzz4l_l2` | HZZ4l | L2 | `shared_manifest` | `exactly4lep`, data/background/signal samples, per-sample `max_files=5` default | `--suite hzz` |
| `tasks_public/t007_hzz4l_l3` | HZZ4l | L3 | `shared_manifest` | `exactly4lep`, data/background/signal samples, per-sample `max_files=5` default | `--suite hzz` |

For scenario runs, `task_overrides` may change `mode`, `input_strategy`,
`max_files`, `solver_backend`, or `solver_model` without changing the checked-in
task package. In downloader and scenario config, `max_files = 0` means no local
cap. For HZZ4l multi-sample tasks, that cap is interpreted per sample group.

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

Artifact keys must match the task's declared contract. Required artifacts must
be present, optional artifacts are allowed only if declared, and undeclared
artifact names are rejected. The Green Agent materializes each artifact into the
task run directory and validates the directory against `submission_contract.yaml`.

`submission_trace.json` is one artifact inside the bundle; it is not a separate
public response mode. The bundle parser also keeps `submission_bundle_v1` small:
it is for structured reports and references, not bulk data transfer.

## Scoring Model

Local public scoring is reproducible without private rubric access:

- `public_scores.contract_pass`
- `public_scores.public_structure_score`
- `public_scores.public_artifact_score`

Official-like scoring may also include:

- `hidden_scores.hidden_quality_score`
- `dimension_scores.execution`
- `dimension_scores.pipeline`
- `dimension_scores.implementation`
- `dimension_scores.reasoning`
- `dimension_scores.analysis`
- `dimension_scores.validation`
- `score_visibility: official_with_hidden`

Private rubrics are not stored in `tasks_public`. `GREEN_SECRETS_JSON` contains
task-specific private rubrics and the expected public contract hash. If the
current public contract hash does not match the secret entry, the private rubric
is ignored. If no matching private rubric is available, a public-contract-passing
task returns an explainable public-only score instead of silently collapsing to
zero.

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

Competition-style shared-input request:

```json
{
  "participants": {
    "purple_agent": "http://purple-agent:9009/"
  },
  "solver_backend": "agent_2_scifi_oh",
  "config": {
    "task_dirs": [
      "tasks_public/t002_hyy_v5_l1",
      "tasks_public/t003_hyy_v5_l2",
      "tasks_public/t004_hyy_v5_l3"
    ],
    "data_dir": "/home/agent/output",
    "solver_model": "gpt-5.4",
    "input_access_mode": "scenario_shared_mount",
    "shared_input_dir": "/home/agent/output/shared_input/{release}/{dataset}/{skim}",
    "allow_green_download": true,
    "solver_request_timeout_seconds": 1800,
    "persist_payloads": true,
    "task_overrides": {
      "t002_hyy_v5_l1": {
        "enabled": true,
        "mode": "call_white",
        "input_strategy": "shared_manifest",
        "max_files": 5
      }
    }
  }
}
```

`solver_backend` may be top-level or inside `config`. The default is
`agent_1_oh`, which is the OpenHarness backend implemented by the reference
Purple Agent. `solver_model` is sent to the Purple Agent payload when present;
otherwise the benchmark default is `gpt-5`.

## Downloading Shared Input Data

For a realistic local Hyy run, download ATLAS Open Data ROOT files into the
benchmark shared input tree:

```bash
uv run python scripts/download_root_files.py \
  --skim GamGam \
  --max-files 0 \
  --json-output ./shared_input/download_manifest.json
```

By default the files are written to:

```text
shared_input/2025e-13tev-beta/data/GamGam/
```

`--max-files 0` means no local cap. The downloader manifest is for local audit;
the runtime `input_manifest.json` is prepared by the Green Agent or by the
shared-input workflow.

## Private Rubric Secrets

Generate `GREEN_SECRETS_JSON` from the private rubric source:

```bash
uv run python scripts/export_green_secrets.py
```

The exporter defaults to the Hyy and HZZ4l task suites and writes compressed
private rubrics using `private_rubric_yaml_gz_b64`. The Green Agent also accepts
the legacy uncompressed `private_rubric_yaml_b64` format.

By default this updates:

- `hepex-analysisops-benchmark/.env`
- `hepex-analysisops-leaderboard/.env`

Task-family subsets are useful when GitHub Secrets length or focused testing is
more important than exporting the whole suite:

```bash
# Export all currently registered hidden rubrics
uv run python scripts/export_green_secrets.py --suite all

# Export only Hyy L1/L2/L3
uv run python scripts/export_green_secrets.py --suite hyy

# Export only HZZ4l L1/L2/L3
uv run python scripts/export_green_secrets.py --suite hzz
```

For GitHub Secrets, print just the secret value without updating local `.env`
files:

```bash
uv run python scripts/export_green_secrets.py --suite all --dry-run --stdout | tail -n 1
```

Run this whenever `submission_contract.yaml` or the private rubric changes.

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
        ├── input_manifest.json
        ├── green_download_manifest.json
        ├── purple_request.json
        ├── purple_agent_timing.json
        ├── purple_response_raw.txt
        ├── submission_bundle_raw.json
        ├── artifact_manifest.json
        ├── <materialized artifacts>
        ├── judge_input.json
        ├── judge_output.json
        ├── engine_error.txt
        └── solver_work/
```

Some files appear only when relevant: for example, `green_download_manifest.json`
appears when Green manages input download, and `engine_error.txt` appears on
evaluation exceptions. `run_summary.json` is useful for local debugging.
AgentBeats leaderboard ingestion uses the task result JSON emitted by the
leaderboard runner, not raw solver work directories.

## Local End-To-End Workflow

The preferred local and CI-adjacent path runs through the leaderboard wrapper:

```bash
cd ../hepex-analysisops-leaderboard
python3 scripts/local_shared_submit.py \
  --host-input-dir ../hepex-analysisops-benchmark/shared_input/2025e-13tev-beta/data/GamGam \
  --task-id t002_hyy_v5_l1 \
  --max-files 5 \
  --mode call_white \
  --solver-backend agent_2_scifi_oh \
  --build-local-images \
  --submission-prefix scifi-oh-hyy-local
```

That wrapper builds local Green/Purple images when requested, mounts local ROOT
files, runs Docker Compose, archives `output/results.json`, records provenance,
and prepares local-only packaged files. The checked-in leaderboard scenarios
under `../hepex-analysisops-leaderboard/ci-submit/` are the better reference for
GitHub Actions smoke comparisons.

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

## Adding Or Updating A Public Task

1. Create `tasks_public/<task_id>/task_spec.yaml`.
2. Add a solver-facing `solver_prompt.md`.
3. Add `submission_contract.yaml` with `required_outputs`, optional outputs,
   artifact types, and schemas.
4. Add `task_package_manifest.yaml` when publishing the package.
5. Add or update mock bundle fixtures in `src/utils/mock_traces.py`.
6. Add public contract and scoring tests under `tests/`.
7. Run `uv run pytest -q`.
8. If hidden scoring applies, update the private rubric and rerun
   `scripts/export_green_secrets.py`.

## Useful Commands

```bash
# Unit and integration tests
uv run pytest -q

# Run public task package checks
uv run pytest tests/test_public_task_contracts.py -q

# Run HZZ4l multi-sample input tests
uv run pytest tests/test_hzz_multi_sample_inputs.py -q

# Build local Green image
docker build -t hepex-green-agent:local .

# Regenerate compressed GREEN_SECRETS_JSON after rubric or contract changes
uv run python scripts/export_green_secrets.py

# Generate a GitHub Secret value for all tasks
uv run python scripts/export_green_secrets.py --suite all --dry-run --stdout | tail -n 1

# Limit secrets to one task family while testing
uv run python scripts/export_green_secrets.py --suite hyy
uv run python scripts/export_green_secrets.py --suite hzz
```

## Attribution

This benchmark uses ATLAS Open Data released under the CERN Open Data policy.

## License

See `LICENSE`.
