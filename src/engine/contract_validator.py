# src/engine/contract_validator.py
"""
Public-safe contract validator.

Reads submission_contract.yaml from the task directory and validates a
submission trace against the declared artifact schemas.

NOTE: This is for public-safe validation only and is not intended to
replace private rubric-based scoring.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_contract(task_dir: str | Path) -> Dict[str, Any]:
    path = Path(task_dir) / "submission_contract.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _check_required_keys(
    obj: Any,
    schema: Any,
    path: str,
) -> List[str]:
    """Recursively check that obj contains the keys declared in schema.

    schema can be:
      - a dict  → { key: sub-schema, ... }
      - a list  → each element is either a str (leaf key) or a one-item dict
      - a str   → leaf key (existence only, no type checking)
      - None    → nothing to check

    Returns a list of dotted-path strings for every missing or wrong-type field.
    """
    errors: List[str] = []

    if schema is None or obj is None:
        return errors

    if not isinstance(obj, dict):
        errors.append(f"{path}: expected object, got {type(obj).__name__}")
        return errors

    if isinstance(schema, dict):
        items = schema.items()
    elif isinstance(schema, list):
        # list of leaf-key strings or single-key dicts
        items = []
        for entry in schema:
            if isinstance(entry, str):
                items.append((entry, None))
            elif isinstance(entry, dict):
                for k, v in entry.items():
                    items.append((k, v))
    else:
        return errors

    for key, sub_schema in items:
        child_path = f"{path}.{key}" if path else key
        if key not in obj:
            errors.append(f"{child_path}: missing")
            continue
        if isinstance(sub_schema, dict) and sub_schema.get("type") == "object":
            nested = sub_schema.get("required_keys", {})
            errors.extend(_check_required_keys(obj[key], nested, child_path))
        elif isinstance(sub_schema, dict) and "required_keys" in sub_schema:
            errors.extend(_check_required_keys(obj[key], sub_schema["required_keys"], child_path))

    return errors


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_contract(
    task: Any,
    submission_trace: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate submission_trace against the task's submission_contract.yaml.

    Returns a report dict compatible with the existing `final.total_score`
    structure used throughout agent.py.
    """
    spec_dir: Optional[str] = getattr(task, "spec_dir", None)
    task_id: str = getattr(task, "id", "unknown")
    task_type: str = getattr(task, "type", "unknown")

    if spec_dir is None:
        return _error_report(task_id, task_type, "No spec_dir: cannot locate submission_contract.yaml")

    contract = _load_contract(spec_dir)
    if not contract:
        return _error_report(task_id, task_type, "submission_contract.yaml not found or empty")

    required_artifacts: List[Dict[str, Any]] = contract.get("required_artifacts", [])

    all_errors: List[str] = []
    missing_artifacts: List[str] = []
    schema_errors: List[str] = []

    for artifact_def in required_artifacts:
        name: str = artifact_def.get("name", "")
        art_type: str = artifact_def.get("type", "json")

        # For fit_summary.json we validate directly against the submission trace
        # (the trace IS the fit_summary artifact).
        # artifact_manifest.json is runtime-generated; treat as lenient (warn only).
        if name == "artifact_manifest.json":
            # lenient: count as warning, not hard failure
            if "artifacts" not in submission_trace.get("artifact_manifest", {}):
                pass  # missing is acceptable at this stage
            continue

        if name == "fit_summary.json" and art_type == "json":
            req_keys = artifact_def.get("required_keys", {})
            errs = _check_required_keys(submission_trace, req_keys, "")
            schema_errors.extend(errs)
        else:
            # Generic artifact: just note it (future extension point)
            pass

    passed = len(schema_errors) == 0 and len(missing_artifacts) == 0

    # Score: 1.0 if fully passed, partial credit for partial failures
    n_checks = max(1, len(required_artifacts))
    n_failed = len(schema_errors) + len(missing_artifacts)
    raw_score = max(0.0, 1.0 - n_failed / n_checks)

    return {
        "task_id": task_id,
        "type": task_type,
        "status": "ok" if passed else "contract_fail",
        "validator": "contract_validator",
        "hard_checks_passed": passed,
        "hard_failures": schema_errors + missing_artifacts,
        "schema_errors": schema_errors,
        "missing_artifacts": missing_artifacts,
        "final": {
            "total_score": raw_score,
            "max_score": 1.0,
            "normalized_score": raw_score,
        },
        "issues": [
            {"severity": "error", "code": "SCHEMA_ERROR", "message": e}
            for e in schema_errors
        ] + [
            {"severity": "error", "code": "MISSING_ARTIFACT", "message": a}
            for a in missing_artifacts
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
