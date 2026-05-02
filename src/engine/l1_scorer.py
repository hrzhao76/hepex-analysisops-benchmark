from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .llm_judge import BaseJudge


LEVEL_DIMENSIONS: Dict[str, List[str]] = {
    "l1": ["execution", "pipeline", "implementation", "reasoning", "analysis", "validation"],
}


def _load_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _load_markdown_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _stage_ids(trace: Dict[str, Any]) -> List[str]:
    return [entry.get("stage_id") for entry in trace.get("workflow_stages", []) if isinstance(entry, dict)]


def _stage_map(trace: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for entry in trace.get("workflow_stages", []):
        if isinstance(entry, dict) and isinstance(entry.get("stage_id"), str):
            result[entry["stage_id"]] = entry
    return result


def _cut_map(trace: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for entry in trace.get("cuts_applied", []):
        if isinstance(entry, dict) and isinstance(entry.get("cut_id"), str):
            result[entry["cut_id"]] = entry
    return result


def _match_value(lhs: Any, rhs: Any) -> bool:
    if isinstance(lhs, (int, float)) and isinstance(rhs, (int, float)):
        return float(lhs) == float(rhs)
    return lhs == rhs


def _match_subset(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(k in actual and _match_subset(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return False
        return all(_match_subset(a, e) for a, e in zip(actual, expected))
    return _match_value(actual, expected)


def _score_deterministic(
    condition: Dict[str, Any],
    submission_dir: Path,
    trace: Dict[str, Any],
    artifacts: Dict[str, Dict[str, Any]],
) -> Tuple[float, Dict[str, Any]]:
    if "required_outputs" in condition:
        missing = [
            output["canonical_filename"]
            for output in condition["required_outputs"]
            if not (submission_dir / output["canonical_filename"]).exists()
        ]
        return (1.0 if not missing else 0.0, {"missing": missing})

    if "object_definition" in condition:
        actual = trace.get("object_definition", {})
        ok = _match_subset(actual, condition["object_definition"])
        return (1.0 if ok else 0.0, {"actual": actual})

    if "selection_cuts" in condition:
        cuts = _cut_map(trace)
        failures = []
        for expected in condition["selection_cuts"]:
            actual = cuts.get(expected["cut_id"])
            if not actual:
                failures.append({"cut_id": expected["cut_id"], "reason": "missing"})
                continue
            for key, value in expected.items():
                if not _match_subset(actual.get(key), value):
                    failures.append(
                        {
                            "cut_id": expected["cut_id"],
                            "field": key,
                            "expected": value,
                            "actual": actual.get(key),
                        }
                    )
                    break
        return (1.0 if not failures else 0.0, {"failures": failures})

    if "derived_observables" in condition or "primary_observable" in condition or "histogram" in condition:
        actual = {
            "derived_observables": trace.get("derived_observables", []),
            "primary_observable": trace.get("primary_observable", trace.get("observable_constructed", {})),
            "histogram": trace.get("histogram_definition", {}),
        }
        expected = {
            "derived_observables": condition.get("derived_observables", []),
            "primary_observable": condition.get("primary_observable", {}),
            "histogram": condition.get("histogram", {}),
        }
        ok = _match_subset(actual, expected)
        return (1.0 if ok else 0.0, {"actual": actual})

    if "inference" in condition:
        actual = trace.get("fit_model_family_used", {})
        expected = {
            "signal": condition["inference"].get("signal_model", {}).get("family"),
            "background": condition["inference"].get("background_model", {}).get("family"),
            "background_order": condition["inference"].get("background_model", {}).get("order"),
            "fit_range_GeV": condition["inference"].get("fit_range"),
            "weighting_scheme": condition["inference"].get("weighting", {}).get("scheme"),
        }
        ok = _match_subset(actual, expected)
        return (1.0 if ok else 0.0, {"actual": actual})

    if "artifact_id" in condition and "field" in condition and "expected_range" in condition:
        artifact_id = condition["artifact_id"]
        field = condition["field"]
        actual_artifact = artifacts.get(artifact_id, {})
        value = actual_artifact.get(field)
        lo, hi = condition["expected_range"]
        ok = isinstance(value, (int, float)) and float(lo) <= float(value) <= float(hi)
        return (1.0 if ok else 0.0, {"value": value, "expected_range": [lo, hi]})

    return (0.0, {"reason": "unsupported_deterministic_condition"})


def _score_structural(condition: Dict[str, Any], trace: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    if "required_stages" in condition:
        present = _stage_ids(trace)
        missing = [stage for stage in condition["required_stages"] if stage not in present]
        return (1.0 if not missing else 0.0, {"present": present, "missing": missing})

    if "ordered_stage_pairs" in condition:
        present = _stage_ids(trace)
        failed_pairs = []
        for first, second in condition["ordered_stage_pairs"]:
            if first not in present or second not in present or present.index(first) >= present.index(second):
                failed_pairs.append([first, second])
        return (1.0 if not failed_pairs else 0.0, {"present": present, "failed_pairs": failed_pairs})

    if "dependencies" in condition:
        stages = _stage_map(trace)
        failed = []
        for entry in condition["dependencies"]:
            stage_id = entry["stage_id"]
            actual = stages.get(stage_id, {}).get("depends_on", [])
            expected = entry.get("depends_on", [])
            if sorted(actual) != sorted(expected):
                failed.append({"stage_id": stage_id, "expected": expected, "actual": actual})
        return (1.0 if not failed else 0.0, {"failed": failed})

    return (0.0, {"reason": "unsupported_structural_condition"})


def _score_heuristic(condition: Dict[str, Any], artifacts: Dict[str, Dict[str, Any]]) -> Tuple[float, Dict[str, Any]]:
    artifact = artifacts.get(condition.get("artifact_id", ""), {})
    x_values = artifact.get(condition.get("x_field", ""), [])
    y_values = artifact.get(condition.get("y_field", ""), [])
    if not isinstance(x_values, list) or not isinstance(y_values, list) or len(x_values) != len(y_values):
        return (0.0, {"reason": "missing_or_misaligned_residual_data"})

    roi_lo, roi_hi = condition.get("region_of_interest", [None, None])
    pref_lo, pref_hi = condition.get("preferred_center_range", [None, None])
    roi_points = [
        (float(x), float(y))
        for x, y in zip(x_values, y_values)
        if isinstance(x, (int, float)) and isinstance(y, (int, float)) and roi_lo <= float(x) <= roi_hi
    ]
    if not roi_points:
        return (0.0, {"reason": "no_points_in_roi"})

    peak_x, peak_y = max(roi_points, key=lambda item: item[1])
    ok = peak_y > 0 and pref_lo <= peak_x <= pref_hi
    return (1.0 if ok else 0.0, {"peak_x": peak_x, "peak_y": peak_y})


def _score_llm_judge(
    condition: Dict[str, Any],
    trace: Dict[str, Any],
    artifacts: Dict[str, Dict[str, Any]],
    interpretation: str,
    judge: Optional[BaseJudge],
) -> Tuple[float, Dict[str, Any]]:
    if judge is None:
        return (0.0, {"reason": "judge_unavailable"})

    evidence = {
        "submission_trace": trace,
        "interpretation": interpretation,
    }
    for entry in condition.get("evidence_inputs", []):
        artifact_id = entry.get("artifact_id")
        if artifact_id == "interpretation":
            evidence["interpretation"] = interpretation
        elif artifact_id:
            evidence[artifact_id] = artifacts.get(artifact_id, {})

    judge_spec = {
        "rubric": {},
        "eval_ref": {},
        "judge_prompt": (
            "You are grading logical consistency for a benchmark submission.\n"
            "Judge rubric:\n{{RUBRIC}}\n"
            "Submission evidence:\n{{SUBMISSION_EVIDENCE}}\n"
            "Return JSON with keys: pass (boolean), explanation (string), notes (array).\n"
        ),
    }
    result = judge.judge(
        judge_spec,
        {"evidence": evidence, "judge_rubric": condition.get("judge_rubric", {})},
        {},
        [],
    )
    if not result.ok or not isinstance(result.parsed, dict):
        return (0.0, {"reason": result.error})
    passed = bool(result.parsed.get("pass"))
    return (1.0 if passed else 0.0, {"judge_result": result.parsed})


def expected_dimensions(task: Any, rubric: Optional[Dict[str, Any]] = None) -> List[str]:
    dims: List[str] = []
    level = getattr(task, "level", None)
    if isinstance(level, str):
        dims.extend(LEVEL_DIMENSIONS.get(level, []))

    rubric = rubric or {}
    weights = rubric.get("weights", {}) or {}
    checks = rubric.get("checks", {}) or {}

    for source in (weights.keys(), checks.keys()):
        for dimension in source:
            if isinstance(dimension, str) and dimension not in dims:
                dims.append(dimension)

    return dims


def rubric_unavailable_report(
    task: Any,
    contract_report: Dict[str, Any],
    *,
    reason: str,
) -> Dict[str, Any]:
    dimensions = expected_dimensions(task)
    task_id = getattr(task, "id", "unknown")
    task_type = getattr(task, "type", "unknown")
    contract_pass = 1.0 if contract_report.get("hard_checks_passed", False) else 0.0

    return {
        "task_id": task_id,
        "type": task_type,
        "status": "public_ok_hidden_unavailable" if contract_pass else "contract_fail",
        "hard_checks_passed": bool(contract_report.get("hard_checks_passed", False)),
        "contract_report": contract_report,
        "public_scores": {
            "contract_pass": contract_pass,
            "public_structure_score": contract_pass,
            "public_artifact_score": contract_pass,
        },
        "hidden_scores": {
            "hidden_quality_score": None,
            "status": "unavailable",
            "reason": reason,
        },
        "score_visibility": "public_only",
        "dimension_scores": {dimension: None for dimension in dimensions},
        "check_results": [],
        "final": {
            "total_score": contract_pass,
            "max_score": 1.0,
            "normalized_score": contract_pass,
        },
        "issues": list(contract_report.get("issues", [])) + [
            {
                "severity": "info",
                "code": "PRIVATE_RUBRIC_UNAVAILABLE",
                "message": reason,
            }
        ],
    }


def score_submission(
    task: Any,
    submission_dir: Path,
    rubric: Dict[str, Any],
    contract_report: Dict[str, Any],
    *,
    judge: Optional[BaseJudge] = None,
) -> Dict[str, Any]:
    trace = _load_json_if_exists(submission_dir / "submission_trace.json")
    artifacts = {
        "diphoton_mass_spectrum": _load_json_if_exists(submission_dir / "diphoton_mass_spectrum.json"),
        "diphoton_fit_summary": _load_json_if_exists(submission_dir / "diphoton_fit_summary.json"),
        "data_minus_background": _load_json_if_exists(submission_dir / "data_minus_background.json"),
    }
    interpretation = _load_markdown_if_exists(submission_dir / "interpretation.md")

    dimension_scores: Dict[str, float] = {
        dimension: 0.0 for dimension in expected_dimensions(task, rubric)
    }
    check_results: List[Dict[str, Any]] = []

    for dimension, checks in (rubric.get("checks", {}) or {}).items():
        if dimension == "validation":
            dimension_scores[dimension] = 0.0
            continue
        weighted_sum = 0.0
        score_weight_sum = 0.0
        for check in checks or []:
            ctype = check.get("type")
            condition = check.get("condition", {}) or {}
            if ctype == "deterministic":
                achieved, evidence = _score_deterministic(condition, submission_dir, trace, artifacts)
            elif ctype == "structural":
                achieved, evidence = _score_structural(condition, trace)
            elif ctype == "heuristic":
                achieved, evidence = _score_heuristic(condition, artifacts)
            elif ctype == "llm_judge":
                achieved, evidence = _score_llm_judge(condition, trace, artifacts, interpretation, judge)
            else:
                achieved, evidence = (0.0, {"reason": f"unsupported_check_type:{ctype}"})

            check_weight = float(check.get("score", 1.0))
            weighted_sum += achieved * check_weight
            score_weight_sum += check_weight
            check_results.append(
                {
                    "dimension": dimension,
                    "id": check.get("id", "unknown"),
                    "type": ctype,
                    "passed": bool(achieved),
                    "score_awarded": achieved * check_weight,
                    "score_max": check_weight,
                    "evidence": evidence,
                }
            )

        dimension_scores[dimension] = 0.0 if score_weight_sum == 0 else weighted_sum / score_weight_sum

    weights = rubric.get("weights", {}) or {}
    total_score = sum(float(weights.get(dimension, 0.0)) * float(score) for dimension, score in dimension_scores.items())
    hard_checks_passed = contract_report.get("status") == "ok"
    if not hard_checks_passed:
        total_score = 0.0

    return {
        "task_id": getattr(task, "id", "unknown"),
        "type": getattr(task, "type", "unknown"),
        "status": "ok" if hard_checks_passed else "contract_fail",
        "hard_checks_passed": hard_checks_passed,
        "contract_report": contract_report,
        "public_scores": {
            "contract_pass": 1.0 if hard_checks_passed else 0.0,
            "public_structure_score": 1.0 if hard_checks_passed else 0.0,
            "public_artifact_score": 1.0 if hard_checks_passed else 0.0,
        },
        "hidden_scores": {
            "hidden_quality_score": float(total_score),
            "status": "ok" if hard_checks_passed else "contract_fail",
        },
        "score_visibility": "official_with_hidden",
        "dimension_scores": dimension_scores,
        "check_results": check_results,
        "final": {
            "total_score": float(total_score),
            "max_score": 1.0,
            "normalized_score": float(total_score),
        },
    }
