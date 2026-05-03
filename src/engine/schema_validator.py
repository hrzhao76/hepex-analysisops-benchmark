from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"

ARTIFACT_TYPES = {"json", "markdown", "text", "image_ref", "table_json"}
FIELD_TYPES = {
    "string",
    "boolean",
    "float",
    "integer",
    "number",
    "object",
    "array_float",
    "array_int",
    "array_number",
    "array_string",
    "array_object",
    "array_float_len_2",
}
CHECK_TYPES = {"deterministic", "structural", "heuristic", "llm_judge"}
CONDITION_KEYS = {
    "required_outputs",
    "required_files",
    "files_nonempty",
    "file_nonempty",
    "object_definition",
    "selection_cuts",
    "selection_constraints",
    "derived_observables",
    "primary_observable",
    "histogram",
    "inference",
    "artifact_id",
    "artifact_numeric_field_range",
    "artifact_value_in_range",
    "artifact_field_constraints",
    "artifact_histogram_properties",
    "artifact_numeric_relationships",
    "artifact_window_consistency",
    "artifact_series_usable",
    "required_stages",
    "ordered_stage_pairs",
    "dependencies",
    "trace_required_fields",
    "trace_stage_families_present",
    "trace_stage_family_order",
    "trace_data_assembly_semantics",
    "trace_data_scope_coverage",
    "data_scope_coverage",
    "workflow_evidence_present",
    "workflow_partial_order",
    "trace_file",
    "trace_observable_construction",
    "observable_match",
    "scientifically_valid_selection_evidence",
    "mc_weighting_strategy",
    "trace_mass_dependent_selection",
    "inference_method_acceptable",
    "scientifically_valid_method_any_of",
    "required_signal_target",
    "compatible_with_required_outputs",
    "localized_excess_in_residual",
    "residual_signal_region_check",
    "cross_artifact_region_consistency",
    "model_data_coherence",
    "histogram_excess_in_region",
    "histogram_peak_location",
    "validation_evidence_any",
    "hzz_sample_manifest_coverage",
    "validation_targets_signal_inference",
    "interpretation_consistency",
    "concise_scientific_interpretation",
    "file",
    "rubric",
    "judge_rubric",
}
EVALUATION_MODES = {"directory_contract_and_private_l1", "directory_contract_and_private_rubric_v1"}
SOLVER_RESPONSE_MODES = {"submission_bundle_v1"}
INPUT_STRATEGIES = {"download", "shared_manifest"}
MODES = {"mock", "call_white"}


class SchemaValidationError(ValueError):
    pass


def load_schema(name: str) -> dict[str, Any]:
    path = SCHEMA_DIR / name
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_mapping(value: Any) -> bool:
    return isinstance(value, dict)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dot_get(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def require_valid(issues: list[str], *, label: str) -> None:
    if issues:
        raise SchemaValidationError(f"{label} failed schema validation: " + "; ".join(issues))


def validate_task_spec_document(data: Any) -> list[str]:
    issues: list[str] = []
    if not _is_mapping(data):
        return ["task_spec must be a mapping"]

    task_id = data.get("id") or _dot_get(data, "task.id")
    if not isinstance(task_id, str) or not task_id.strip():
        issues.append("task_spec requires id or task.id")

    if "mode" in data and data["mode"] not in MODES:
        issues.append(f"mode must be one of {sorted(MODES)}")
    if "input_strategy" in data and data["input_strategy"] not in INPUT_STRATEGIES:
        issues.append(f"input_strategy must be one of {sorted(INPUT_STRATEGIES)}")
    if "solver_response_mode" in data and data["solver_response_mode"] not in SOLVER_RESPONSE_MODES:
        issues.append(f"solver_response_mode must be one of {sorted(SOLVER_RESPONSE_MODES)}")
    if "evaluation_mode" in data and data["evaluation_mode"] not in EVALUATION_MODES:
        issues.append(f"evaluation_mode must be one of {sorted(EVALUATION_MODES)}")
    if "input_requirements" in data and not isinstance(data["input_requirements"], dict):
        issues.append("input_requirements must be a mapping")
    input_requirements = data.get("input_requirements", {})
    if isinstance(input_requirements, dict):
        if "samples" in input_requirements:
            samples = input_requirements["samples"]
            if not isinstance(samples, list):
                issues.append("input_requirements.samples must be a list")
            else:
                for idx, sample in enumerate(samples):
                    label = f"input_requirements.samples[{idx}]"
                    if not isinstance(sample, dict):
                        issues.append(f"{label} must be a mapping")
                        continue
                    if not isinstance(sample.get("name"), str) or not sample["name"].strip():
                        issues.append(f"{label}.name is required")
                    if sample.get("role") not in {"data", "background", "signal"}:
                        issues.append(f"{label}.role must be data, background, or signal")
                    if not isinstance(sample.get("dids"), list) or not sample["dids"]:
                        issues.append(f"{label}.dids must be a non-empty list")
        if "sample_groups" in input_requirements:
            sample_groups = input_requirements["sample_groups"]
            if not isinstance(sample_groups, list):
                issues.append("input_requirements.sample_groups must be a list")
            else:
                for idx, group in enumerate(sample_groups):
                    label = f"input_requirements.sample_groups[{idx}]"
                    if not isinstance(group, dict):
                        issues.append(f"{label} must be a mapping")
                        continue
                    if not isinstance(group.get("id"), str) or not group["id"].strip():
                        issues.append(f"{label}.id is required")
                    if not isinstance(group.get("label"), str) or not group["label"].strip():
                        issues.append(f"{label}.label is required")
                    if group.get("role") not in {"data", "background", "signal"}:
                        issues.append(f"{label}.role must be data, background, or signal")
                    if not isinstance(group.get("dids"), list) or not group["dids"]:
                        issues.append(f"{label}.dids must be a non-empty list")

    if "scientific_core" in data and not isinstance(data["scientific_core"], dict):
        issues.append("scientific_core must be a mapping when present")
    return issues


def _validate_output_entries(entries: Any, *, field: str, issues: list[str]) -> list[str]:
    filenames: list[str] = []
    if not isinstance(entries, list):
        issues.append(f"{field} must be a list")
        return filenames
    for idx, entry in enumerate(entries):
        label = f"{field}[{idx}]"
        if not isinstance(entry, dict):
            issues.append(f"{label} must be a mapping")
            continue
        filename = entry.get("canonical_filename")
        artifact_type = entry.get("type")
        if not isinstance(filename, str) or not filename:
            issues.append(f"{label}.canonical_filename is required")
        else:
            filenames.append(filename)
        if artifact_type not in ARTIFACT_TYPES:
            issues.append(f"{label}.type must be one of {sorted(ARTIFACT_TYPES)}")
    return filenames


def _validate_field_types(schema: dict[str, Any], *, schema_label: str, issues: list[str]) -> None:
    field_types = schema.get("field_types", {}) or {}
    if not isinstance(field_types, dict):
        issues.append(f"{schema_label}.field_types must be a mapping")
        return
    for field_name, type_name in field_types.items():
        if type_name not in FIELD_TYPES:
            issues.append(f"{schema_label}.field_types.{field_name} uses unsupported type {type_name!r}")


def validate_submission_contract_document(data: Any) -> list[str]:
    issues: list[str] = []
    if not _is_mapping(data):
        return ["submission_contract must be a mapping"]

    required_files = _validate_output_entries(data.get("required_outputs"), field="required_outputs", issues=issues)
    optional_files = _validate_output_entries(data.get("optional_outputs", []), field="optional_outputs", issues=issues)
    all_files = required_files + optional_files
    duplicates = sorted({name for name in all_files if all_files.count(name) > 1})
    if duplicates:
        issues.append(f"duplicate artifact filenames: {duplicates}")

    schemas = data.get("schemas")
    if not isinstance(schemas, dict):
        issues.append("schemas must be a mapping")
        return issues

    missing_required_schemas = [
        name
        for name in required_files
        if name.endswith((".json", ".md")) and name not in schemas
    ]
    if missing_required_schemas:
        issues.append(f"missing schemas for required artifacts: {missing_required_schemas}")

    extra_schemas = sorted(set(schemas) - set(all_files))
    if extra_schemas:
        issues.append(f"schemas declared for undeclared artifacts: {extra_schemas}")

    for filename, schema in schemas.items():
        if not isinstance(schema, dict):
            issues.append(f"schemas.{filename} must be a mapping")
            continue
        _validate_field_types(schema, schema_label=f"schemas.{filename}", issues=issues)
        nested = schema.get("nested_required_fields", {}) or {}
        if not isinstance(nested, dict):
            issues.append(f"schemas.{filename}.nested_required_fields must be a mapping")
            continue
        for nested_name, nested_schema in nested.items():
            if isinstance(nested_schema, dict):
                _validate_field_types(
                    nested_schema,
                    schema_label=f"schemas.{filename}.nested_required_fields.{nested_name}",
                    issues=issues,
                )
    return issues


def validate_private_rubric_document(data: Any) -> list[str]:
    issues: list[str] = []
    if not _is_mapping(data):
        return ["private_rubric must be a mapping"]

    if "version" not in data:
        issues.append("version is required")
    weights = data.get("weights")
    checks = data.get("checks")
    if not isinstance(weights, dict):
        issues.append("weights must be a mapping")
    if not isinstance(checks, dict):
        issues.append("checks must be a mapping")
        return issues

    for dimension, entries in checks.items():
        if not isinstance(entries, list):
            issues.append(f"checks.{dimension} must be a list")
            continue
        for idx, check in enumerate(entries):
            label = f"checks.{dimension}[{idx}]"
            if not isinstance(check, dict):
                issues.append(f"{label} must be a mapping")
                continue
            if not isinstance(check.get("id"), str):
                issues.append(f"{label}.id is required")
            if check.get("type") not in CHECK_TYPES:
                issues.append(f"{label}.type must be one of {sorted(CHECK_TYPES)}")
            if "score" not in check:
                issues.append(f"{label}.score is required")
            condition = check.get("condition", {}) or {}
            if not isinstance(condition, dict):
                issues.append(f"{label}.condition must be a mapping")
                continue
            if check.get("type") != "llm_judge" and not (set(condition) & CONDITION_KEYS):
                issues.append(f"{label}.condition has no supported condition family")
    return issues


def validate_submission_bundle_document(data: Any) -> list[str]:
    if not _is_mapping(data):
        return ["submission_bundle must be a mapping"]
    if not isinstance(data.get("artifacts"), dict):
        return ["artifacts must be a mapping"]
    return []


def validate_input_manifest_document(data: Any) -> list[str]:
    issues: list[str] = []
    if not _is_mapping(data):
        return ["input_manifest must be a mapping"]
    if not isinstance(data.get("task_id"), str):
        issues.append("task_id is required")
    files = data.get("files")
    if not isinstance(files, list):
        issues.append("files must be a list")
        return issues
    for idx, entry in enumerate(files):
        if not isinstance(entry, dict):
            issues.append(f"files[{idx}] must be a mapping")
            continue
        if not isinstance(entry.get("logical_name"), str):
            issues.append(f"files[{idx}].logical_name is required")
        if not isinstance(entry.get("path"), str):
            issues.append(f"files[{idx}].path is required")
        if "samples" in data:
            if not isinstance(entry.get("sample_id"), str):
                issues.append(f"files[{idx}].sample_id is required for multi-sample manifests")
            if not isinstance(entry.get("sample_name"), str):
                issues.append(f"files[{idx}].sample_name is required for multi-sample manifests")
            if entry.get("sample_role") not in {"data", "background", "signal"}:
                issues.append(f"files[{idx}].sample_role must be data, background, or signal")
            if "did" not in entry:
                issues.append(f"files[{idx}].did is required for multi-sample manifests")
            if not isinstance(entry.get("is_data"), bool):
                issues.append(f"files[{idx}].is_data is required for multi-sample manifests")
            if not isinstance(entry.get("is_mc"), bool):
                issues.append(f"files[{idx}].is_mc is required for multi-sample manifests")
            if not isinstance(entry.get("weight_policy"), str):
                issues.append(f"files[{idx}].weight_policy is required for multi-sample manifests")
        if "sample_groups" in data:
            if not isinstance(entry.get("sample_group_id"), str):
                issues.append(f"files[{idx}].sample_group_id is required for legacy multi-sample manifests")
    samples = data.get("samples")
    if samples is not None:
        if not isinstance(samples, list):
            issues.append("samples must be a list")
        else:
            for idx, sample in enumerate(samples):
                label = f"samples[{idx}]"
                if not isinstance(sample, dict):
                    issues.append(f"{label} must be a mapping")
                    continue
                if not isinstance(sample.get("id"), str):
                    issues.append(f"{label}.id is required")
                if not isinstance(sample.get("name"), str):
                    issues.append(f"{label}.name is required")
                if sample.get("role") not in {"data", "background", "signal"}:
                    issues.append(f"{label}.role must be data, background, or signal")
                if not isinstance(sample.get("dids"), list):
                    issues.append(f"{label}.dids must be a list")
    sample_groups = data.get("sample_groups")
    if sample_groups is not None:
        if not isinstance(sample_groups, list):
            issues.append("sample_groups must be a list")
        else:
            for idx, group in enumerate(sample_groups):
                label = f"sample_groups[{idx}]"
                if not isinstance(group, dict):
                    issues.append(f"{label} must be a mapping")
                    continue
                if not isinstance(group.get("id"), str):
                    issues.append(f"{label}.id is required")
                if not isinstance(group.get("label"), str):
                    issues.append(f"{label}.label is required")
                if group.get("role") not in {"data", "background", "signal"}:
                    issues.append(f"{label}.role must be data, background, or signal")
                if not isinstance(group.get("dids"), list):
                    issues.append(f"{label}.dids must be a list")
    return issues


def validate_task_package_manifest_document(
    data: Any,
    *,
    package_dir: Path | None = None,
    check_hashes: bool = True,
) -> list[str]:
    issues: list[str] = []
    if not _is_mapping(data):
        return ["task_package_manifest must be a mapping"]

    for field in ("schema_version", "package_id", "task_id", "source", "status", "schema_versions", "files"):
        if field not in data:
            issues.append(f"{field} is required")
    if data.get("source") not in {"manual", "generated", "curated", "published"}:
        issues.append("source must be manual, generated, curated, or published")
    if data.get("status") not in {"draft", "curated", "published"}:
        issues.append("status must be draft, curated, or published")
    if not isinstance(data.get("schema_versions"), dict):
        issues.append("schema_versions must be a mapping")

    files = data.get("files", {})
    if not isinstance(files, dict):
        issues.append("files must be a mapping")
        return issues
    for group_name in ("public", "private"):
        entries = files.get(group_name, []) or []
        if not isinstance(entries, list):
            issues.append(f"files.{group_name} must be a list")
            continue
        for idx, entry in enumerate(entries):
            label = f"files.{group_name}[{idx}]"
            if not isinstance(entry, dict):
                issues.append(f"{label} must be a mapping")
                continue
            rel_path = entry.get("path")
            if not isinstance(rel_path, str) or not rel_path:
                issues.append(f"{label}.path is required")
                continue
            if package_dir is None:
                continue
            path = package_dir / rel_path
            if not path.exists():
                issues.append(f"{label}.path does not exist: {rel_path}")
                continue
            expected_hash = entry.get("sha256")
            if check_hashes and expected_hash and sha256_file(path) != expected_hash:
                issues.append(f"{label}.sha256 mismatch for {rel_path}")
    return issues


def validate_task_package_dir(
    task_dir: str | Path,
    *,
    require_manifest: bool = False,
    check_hashes: bool = True,
) -> list[str]:
    task_dir = Path(task_dir)
    issues: list[str] = []

    spec_path = task_dir / "task_spec.yaml"
    if spec_path.exists():
        issues.extend(
            f"task_spec.yaml: {issue}"
            for issue in validate_task_spec_document(yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {})
        )

    contract_path = task_dir / "submission_contract.yaml"
    if contract_path.exists():
        issues.extend(
            f"submission_contract.yaml: {issue}"
            for issue in validate_submission_contract_document(
                yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
            )
        )

    manifest_path = task_dir / "task_package_manifest.yaml"
    if not manifest_path.exists():
        if require_manifest:
            issues.append("task_package_manifest.yaml is required")
        return issues

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    issues.extend(
        f"task_package_manifest.yaml: {issue}"
        for issue in validate_task_package_manifest_document(
            manifest,
            package_dir=task_dir,
            check_hashes=check_hashes,
        )
    )
    return issues
