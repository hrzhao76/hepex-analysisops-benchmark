# src/engine/contract_validator.py
"""
Public-safe contract validator.

Reads submission_contract.yaml from the task directory and validates a
materialized submission directory against the declared artifact schemas.

NOTE: This is for public-safe validation only and is not intended to
replace private rubric-based scoring.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

TYPE_NAMES = {
    "string": str,
    "boolean": bool,
    "float": (int, float),
    "integer": int,
    "number": (int, float),
    "object": dict,
    "array_float": list,
    "array_int": list,
    "array_number": list,
    "array_string": list,
    "array_object": list,
    "array_float_len_2": list,
}

JSON_ARTIFACT_TYPES = {"json", "table_json", "image_ref"}
TEXT_ARTIFACT_TYPES = {"markdown", "text"}


def _load_json(path: Path) -> Any:
    import json
    return json.loads(path.read_text(encoding="utf-8"))


def _get_value(obj: Any, field: str) -> Any:
    current = obj
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(field)
        current = current[part]
    return current


def _validate_required_fields(data: dict[str, Any], fields: list[str], errors: list[str], prefix: str = "") -> None:
    for field in fields:
        label = f"{prefix}{field}" if not prefix else f"{prefix}.{field}"
        try:
            _get_value(data, field)
        except KeyError:
            errors.append(f"{label}: missing")


def _validate_type(value: Any, type_name: str) -> bool:
    expected = TYPE_NAMES.get(type_name)
    if expected is None:
        return True
    if type_name == "array_float":
        return isinstance(value, list) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    if type_name == "array_int":
        return isinstance(value, list) and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
    if type_name == "array_number":
        return isinstance(value, list) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    if type_name == "array_string":
        return isinstance(value, list) and all(isinstance(v, str) for v in value)
    if type_name == "array_object":
        return isinstance(value, list) and all(isinstance(v, dict) for v in value)
    if type_name == "array_float_len_2":
        return isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in value)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, expected)


def _validate_field_types(data: dict[str, Any], field_types: dict[str, str], errors: list[str], prefix: str = "") -> None:
    for field, type_name in field_types.items():
        label = f"{prefix}{field}" if not prefix else f"{prefix}.{field}"
        try:
            value = _get_value(data, field)
        except KeyError:
            continue
        if not _validate_type(value, type_name):
            errors.append(f"{label}: expected {type_name}")


def _validate_constraints(data: dict[str, Any], constraints: dict[str, Any], errors: list[str]) -> None:
    for field, rule in constraints.items():
        if field in {"array_alignment", "array_lengths"}:
            for entry in rule or []:
                fields = entry.get("fields", [])
                relation = entry.get("relation", entry.get("relationship"))
                try:
                    values = [_get_value(data, name) for name in fields]
                except KeyError:
                    continue
                if len(values) < 2 or not all(hasattr(value, "__len__") for value in values):
                    continue
                if relation == "same_length" and len(values[0]) != len(values[1]):
                    errors.append(f"{fields}: expected same_length")
                if relation == "edges_equals_counts_plus_one" and len(values[0]) != len(values[1]) + 1:
                    errors.append(f"{fields}: expected edges_equals_counts_plus_one")
            continue
        try:
            value = _get_value(data, field)
        except KeyError:
            continue
        if isinstance(rule, dict):
            min_length = rule.get("min_length")
            max_length = rule.get("max_length")
            gt = rule.get("gt")
            contains_all = rule.get("contains_all")
            if min_length is not None and hasattr(value, "__len__") and len(value) < min_length:
                errors.append(f"{field}: expected min_length {min_length}")
            if max_length is not None and hasattr(value, "__len__") and len(value) > max_length:
                errors.append(f"{field}: expected max_length {max_length}")
            if gt is not None and not (isinstance(value, (int, float)) and not isinstance(value, bool) and value > gt):
                errors.append(f"{field}: expected > {gt}")
            if contains_all is not None and isinstance(value, list):
                missing = [item for item in contains_all if item not in value]
                if missing:
                    errors.append(f"{field}: missing required values {missing}")


def _validate_nested_fields(data: dict[str, Any], nested_spec: dict[str, Any], errors: list[str]) -> None:
    for field, spec in nested_spec.items():
        try:
            value = _get_value(data, field)
        except KeyError:
            continue
        if isinstance(value, list):
            for idx, entry in enumerate(value):
                if not isinstance(entry, dict):
                    errors.append(f"{field}[{idx}]: expected object")
                    continue
                _validate_required_fields(entry, spec.get("required_fields", []), errors, f"{field}[{idx}]")
                _validate_field_types(entry, spec.get("field_types", {}), errors, f"{field}[{idx}]")
        elif isinstance(value, dict):
            _validate_required_fields(value, spec.get("required_fields", []), errors, field)
            _validate_field_types(value, spec.get("field_types", {}), errors, field)


def _validate_markdown(path: Path, schema: dict[str, Any], errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8")
    constraints = schema.get("constraints", {})
    if constraints.get("non_empty") and not text.strip():
        errors.append(f"{path.name}: expected non-empty markdown")
    min_characters = constraints.get("min_characters")
    if min_characters is not None and len(text.strip()) < min_characters:
        errors.append(f"{path.name}: expected at least {min_characters} characters")


def _validate_text(path: Path, schema: dict[str, Any], errors: list[str]) -> None:
    _validate_markdown(path, schema, errors)


def _validate_json_artifact(path: Path, schema: dict[str, Any], errors: list[str]) -> None:
    import json
    try:
        data = _load_json(path)
    except json.JSONDecodeError as exc:
        errors.append(f"{path.name}: invalid JSON ({exc.msg})")
        return
    if not isinstance(data, dict):
        errors.append(f"{path.name}: expected top-level object")
        return
    _validate_required_fields(data, schema.get("required_fields", []), errors)
    _validate_field_types(data, schema.get("field_types", {}), errors)
    _validate_nested_fields(data, schema.get("nested_required_fields", {}), errors)
    _validate_constraints(data, schema.get("constraints", {}), errors)


def _contract_outputs(contract: dict[str, Any], *, required_only: bool = False) -> list[dict[str, Any]]:
    required = [entry for entry in contract.get("required_outputs", []) or [] if isinstance(entry, dict)]
    if required_only:
        return required
    optional = [entry for entry in contract.get("optional_outputs", []) or [] if isinstance(entry, dict)]
    return required + optional


def _validate_artifact(path: Path, artifact_type: str, schema: dict[str, Any], errors: list[str]) -> None:
    if artifact_type == "markdown":
        _validate_markdown(path, schema, errors)
    elif artifact_type == "text":
        _validate_text(path, schema, errors)
    elif artifact_type in JSON_ARTIFACT_TYPES:
        _validate_json_artifact(path, schema, errors)
    else:
        errors.append(f"{path.name}: unsupported artifact type {artifact_type!r}")


def validate_submission_dir(task: Any, submission_dir: str | Path) -> Dict[str, Any]:
    """Validate a materialized submission directory against the task contract."""
    spec_dir: Optional[str] = getattr(task, "spec_dir", None)
    task_id: str = getattr(task, "id", "unknown")
    task_type: str = getattr(task, "type", "unknown")

    if spec_dir is None:
        return _error_report(task_id, task_type, "No spec_dir: cannot locate submission contract")

    contract_rel = getattr(task, "submission_contract_path", "submission_contract.yaml") or "submission_contract.yaml"
    contract_path = Path(spec_dir) / contract_rel
    if not contract_path.exists():
        return _error_report(task_id, task_type, f"submission contract not found: {contract_path.name}")

    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8")) or {}
    submission_dir = Path(submission_dir)
    missing_files: list[str] = []
    schema_errors: list[str] = []

    for artifact in _contract_outputs(contract, required_only=True):
        filename = artifact["canonical_filename"]
        path = submission_dir / filename
        if not path.exists():
            missing_files.append(filename)
            continue
        schema = contract.get("schemas", {}).get(filename, {})
        _validate_artifact(path, artifact.get("type", "json"), schema, schema_errors)

    for artifact in contract.get("optional_outputs", []) or []:
        if not isinstance(artifact, dict):
            continue
        filename = artifact["canonical_filename"]
        path = submission_dir / filename
        if not path.exists():
            continue
        schema = contract.get("schemas", {}).get(filename, {})
        _validate_artifact(path, artifact.get("type", "json"), schema, schema_errors)

    status = "ok" if not missing_files and not schema_errors else "contract_fail"
    return {
        "task_id": task_id,
        "type": task_type,
        "status": status,
        "validator": "contract_validator_dir",
        "hard_checks_passed": status == "ok",
        "missing_files": missing_files,
        "schema_errors": schema_errors,
        "final": {
            "total_score": 1.0 if status == "ok" else 0.0,
            "max_score": 1.0,
            "normalized_score": 1.0 if status == "ok" else 0.0,
        },
        "issues": [
            {"severity": "error", "code": "MISSING_FILE", "message": msg}
            for msg in missing_files
        ] + [
            {"severity": "error", "code": "SCHEMA_ERROR", "message": msg}
            for msg in schema_errors
        ],
    }


def _error_report(task_id: str, task_type: str, msg: str) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "type": task_type,
        "status": "error",
        "validator": "contract_validator",
        "hard_checks_passed": False,
        "error": msg,
        "final": {"total_score": 0.0, "max_score": 1.0, "normalized_score": 0.0},
        "issues": [{"severity": "error", "code": "VALIDATOR_ERROR", "message": msg}],
    }
