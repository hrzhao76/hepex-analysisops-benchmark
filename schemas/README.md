# Benchmark Schemas

These schemas define the public and private file contracts used by the
benchmark runtime and by generated task packages.

- `task_spec.schema.yaml` describes task identity, data/input requirements,
  solver response mode, and evaluation mode.
- `submission_contract.schema.yaml` describes the public artifact protocol:
  required outputs, optional outputs, artifact types, and per-file schemas.
- `submission_bundle.schema.yaml` describes the small JSON response envelope
  returned by Purple agents before artifacts are materialized.
- `private_rubric.schema.yaml` describes the hidden executable rubric consumed
  by the generic scorer.
- `input_manifest.schema.yaml` describes runtime input files without assuming a
  ROOT-only data layout.
- `task_package_manifest.schema.yaml` describes provenance, schema versions,
  file hashes, and generated/manual publication state for a task package.
- `level_profile.schema.yaml` describes the shared L1/L2/L3 policy surface that
  generators should use when deciding hard and soft constraints.

In runtime terms:

- A schema states what a file is allowed to contain.
- A validator rejects malformed tasks, contracts, rubrics, manifests, and
  submissions before scoring.
- A scorer applies a validated private rubric to a validated submission.
- A task package manifest makes a task package reproducible and auditable.
