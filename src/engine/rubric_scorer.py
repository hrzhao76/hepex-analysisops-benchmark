from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .llm_judge import BaseJudge
from .package_loader import load_submission_contract


LEVEL_DIMENSIONS: Dict[str, List[str]] = {
    "l1": ["execution", "pipeline", "implementation", "reasoning", "analysis", "validation"],
    "l2": ["execution", "pipeline", "implementation", "reasoning", "analysis", "validation"],
    "l3": ["execution", "pipeline", "implementation", "reasoning", "analysis", "validation"],
}

FAMILY_KEYWORDS: Dict[str, tuple[str, ...]] = {
    "data_access": ("data", "load", "read", "input", "access", "download"),
    "data_loading": ("data", "load", "read", "input", "access", "download"),
    "object_or_event_selection": ("select", "selection", "cut", "filter", "photon", "event"),
    "selection": ("select", "selection", "cut", "filter", "photon", "event"),
    "observable_construction": ("observable", "mass", "construct", "invariant", "m_yy", "mgg"),
    "mass_construction_or_signal_proxy": ("observable", "mass", "construct", "invariant", "m_yy", "mgg", "proxy"),
    "spectrum_or_summary_construction": ("histogram", "spectrum", "bin", "summary"),
    "spectrum_construction": ("histogram", "spectrum", "bin"),
    "inference_or_signal_localization": ("fit", "inference", "signal", "local", "background", "likelihood"),
    "signal_extraction": ("fit", "inference", "signal", "extract", "likelihood"),
    "residual_or_background_subtraction": ("residual", "background", "subtract"),
    "interpretation": ("interpret", "conclusion", "claim", "report"),
    "validation": ("validate", "validation", "robust", "stability", "cross", "scan"),
}

FAMILY_ALIASES: Dict[str, str] = {
    "data_loading": "data_access",
    "selection": "object_or_event_selection",
    "event_selection": "object_or_event_selection",
    "object_selection": "object_or_event_selection",
    "spectrum_construction": "spectrum_or_summary_construction",
    "histogramming": "spectrum_or_summary_construction",
    "histogram_construction": "spectrum_or_summary_construction",
    "signal_extraction": "inference_or_signal_localization",
    "mass_construction_or_signal_proxy": "observable_construction",
}

FIELD_ALIASES: Dict[str, tuple[str, ...]] = {
    "gaussian_mean_gev": (
        "gaussian_mean_gev",
        "signal_peak_gev",
        "signal_peak_position",
        "signal_peak_mass_GeV",
        "signal_peak_mass_gev",
    ),
    "signal_peak_gev": (
        "signal_peak_gev",
        "gaussian_mean_gev",
        "signal_peak_position",
        "signal_peak_mass_GeV",
        "signal_peak_mass_gev",
    ),
    "fit_peak": (
        "signal_peak_gev",
        "gaussian_mean_gev",
        "signal_peak_position",
        "signal_peak_mass_GeV",
        "signal_peak_mass_gev",
    ),
    "bin_centers": ("bin_centers", "bin_centers_GeV", "bin_centers_gev", "mass_centers_gev"),
    "residual_counts": ("residual_counts", "data_minus_background", "residuals"),
    "bin_edges": ("bin_edges", "bin_edges_GeV", "bin_edges_gev"),
    "bin_counts": ("bin_counts", "counts"),
    "bin_uncertainties": ("bin_uncertainties", "count_uncertainties"),
}


def _load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _load_text_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _get_path(obj: Any, field: str, default: Any = None) -> Any:
    current = obj
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _get_any_field(obj: Any, names: list[str] | tuple[str, ...], default: Any = None) -> Any:
    for name in names:
        value = _get_path(obj, name, default=None)
        if value is not None:
            return value
    return default


def _coerce_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _all_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        values: list[str] = []
        for key, item in value.items():
            values.extend(_all_strings(key))
            values.extend(_all_strings(item))
        return values
    if isinstance(value, list):
        values = []
        for item in value:
            values.extend(_all_strings(item))
        return values
    return []


def _period_key(value: str) -> str | None:
    text = value.strip().lower()
    patterns = [
        r"data(?P<yy>\d{2})[_\-\s]*period(?P<period>[a-z])",
        r"(?P<yyyy>20\d{2})[_\-\s]*(?:period)?[_\-\s]*(?P<period>[a-z])$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        year = match.groupdict().get("yyyy")
        if not year:
            year = f"20{match.group('yy')}"
        return f"{year}_{match.group('period')}"
    return None


def _period_keys_from_trace(trace: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for value in _all_strings(trace):
        period = _period_key(value)
        if period:
            keys.add(period)
    return keys


def _positive_mass_range_evidence(value: Any, path: tuple[str, ...] = ()) -> bool:
    if isinstance(value, dict):
        return any(_positive_mass_range_evidence(item, (*path, str(key).lower())) for key, item in value.items())
    if isinstance(value, list):
        label = ".".join(path)
        if (
            len(value) == 2
            and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in value)
            and any(token in label for token in ("mass", "m_yy", "gev", "range", "window", "region"))
        ):
            return float(value[0]) > 0.0 and float(value[1]) > float(value[0])
        return any(_positive_mass_range_evidence(item, path) for item in value)
    return False


def _artifact_key(entry: dict[str, Any]) -> str:
    filename = str(entry.get("canonical_filename", ""))
    return str(entry.get("artifact_id") or entry.get("name") or Path(filename).stem)


def _contract_outputs(contract: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for section in ("required_outputs", "optional_outputs"):
        entries.extend(entry for entry in contract.get(section, []) or [] if isinstance(entry, dict))
    return entries


def _load_artifacts(submission_dir: Path, contract: dict[str, Any]) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for entry in _contract_outputs(contract):
        filename = entry.get("canonical_filename")
        if not isinstance(filename, str):
            continue
        path = submission_dir / filename
        if not path.exists():
            continue
        artifact_type = entry.get("type", "json")
        if artifact_type in {"markdown", "text"}:
            payload: Any = _load_text_if_exists(path)
        else:
            payload = _load_json_if_exists(path)
        for key in {_artifact_key(entry), filename, Path(filename).stem}:
            if key:
                artifacts[key] = payload
    return artifacts


def _stage_entries(trace: dict[str, Any]) -> list[dict[str, Any]]:
    stages = trace.get("workflow_stages", [])
    return [entry for entry in stages if isinstance(entry, dict)] if isinstance(stages, list) else []


def _stage_ids(trace: Dict[str, Any]) -> List[str]:
    ids: list[str] = []
    for entry in _stage_entries(trace):
        value = entry.get("stage_id", entry.get("stage_label"))
        if isinstance(value, str):
            ids.append(value)
    return ids


def _stage_map(trace: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for entry in _stage_entries(trace):
        for key in ("stage_id", "stage_label"):
            if isinstance(entry.get(key), str):
                result[entry[key]] = entry
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


def _contains_all_tokens(text: str, tokens: list[str]) -> bool:
    normalized = text.lower()
    return all(token.lower() in normalized for token in tokens)


def _stage_family_for_text(text: str) -> str | None:
    normalized = text.lower()
    for family, keywords in FAMILY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return family
    return None


def _stage_families(trace: dict[str, Any]) -> list[str]:
    families: list[str] = []
    for entry in _stage_entries(trace):
        text = " ".join(
            str(entry.get(key, ""))
            for key in ("stage_id", "stage_label", "role", "description", "family")
        )
        explicit = entry.get("family") or entry.get("stage_family")
        family = str(explicit) if explicit else _stage_family_for_text(text)
        if family:
            families.append(family)
    return families


def _family_matches(actual: str, required: str) -> bool:
    actual_norm = FAMILY_ALIASES.get(actual, actual)
    required_norm = FAMILY_ALIASES.get(required, required)
    return actual_norm == required_norm


def _has_family(families: list[str], required: str) -> bool:
    return any(_family_matches(actual, required) for actual in families)


def _score_required_files(files: list[str], submission_dir: Path) -> Tuple[float, Dict[str, Any]]:
    missing = [filename for filename in files if not (submission_dir / filename).exists()]
    return (1.0 if not missing else 0.0, {"missing": missing})


def _score_files_nonempty(files: list[str], submission_dir: Path) -> Tuple[float, Dict[str, Any]]:
    failures = [
        filename
        for filename in files
        if not (submission_dir / filename).exists() or (submission_dir / filename).stat().st_size == 0
    ]
    return (1.0 if not failures else 0.0, {"empty_or_missing": failures})


def _score_numeric_range(spec: dict[str, Any], artifacts: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    filename = spec.get("file") or spec.get("artifact_id")
    field = spec.get("field")
    expected_range = spec.get("expected_range", spec.get("range"))
    if not isinstance(filename, str) or not isinstance(field, str) or not isinstance(expected_range, list) or len(expected_range) != 2:
        return (0.0, {"reason": "invalid_numeric_range_spec"})
    artifact = artifacts.get(filename, {})
    aliases = FIELD_ALIASES.get(field, (field,))
    value = _get_any_field(artifact, aliases)
    lo, hi = expected_range
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) and float(lo) <= float(value) <= float(hi)
    return (1.0 if ok else 0.0, {"value": value, "expected_range": [lo, hi], "field_aliases": list(aliases)})


def _score_histogram_properties(spec: dict[str, Any], artifacts: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    filename = spec.get("file")
    if not isinstance(filename, str):
        return (0.0, {"reason": "missing_file"})
    artifact = artifacts.get(filename, {})
    if not isinstance(artifact, dict):
        return (0.0, {"reason": "missing_artifact"})

    checks: list[bool] = []
    evidence: dict[str, Any] = {}
    expected_range = spec.get("range_gev_equals")
    if expected_range:
        edges = _get_any_field(artifact, FIELD_ALIASES["bin_edges"], [])
        actual_range = [edges[0], edges[-1]] if isinstance(edges, list) and len(edges) >= 2 else _get_any_field(
            artifact,
            ("range_GeV", "range_gev", "fit_range", "fit_range_GeV"),
        )
        evidence["actual_range"] = actual_range
        checks.append(actual_range == expected_range)
    required_coverage = spec.get("range_gev_covers")
    if required_coverage:
        edges = _get_any_field(artifact, FIELD_ALIASES["bin_edges"], [])
        actual_range = [edges[0], edges[-1]] if isinstance(edges, list) and len(edges) >= 2 else _get_any_field(
            artifact,
            ("range_GeV", "range_gev", "fit_range", "fit_range_GeV"),
        )
        evidence["actual_range"] = actual_range
        checks.append(
            isinstance(actual_range, list)
            and len(actual_range) == 2
            and float(actual_range[0]) <= float(required_coverage[0])
            and float(actual_range[1]) >= float(required_coverage[1])
        )
    expected_width = spec.get("bin_width_gev_equals")
    if expected_width is not None:
        width = _get_any_field(artifact, ("bin_width_GeV", "bin_width_gev", "bin_width"))
        if width is None:
            edges = _get_any_field(artifact, FIELD_ALIASES["bin_edges"], [])
            width = round(float(edges[1]) - float(edges[0]), 8) if isinstance(edges, list) and len(edges) >= 2 else None
        evidence["actual_bin_width"] = width
        checks.append(isinstance(width, (int, float)) and abs(float(width) - float(expected_width)) < 1e-6)
    width_range = spec.get("bin_width_gev_between")
    if width_range is not None:
        width = _get_any_field(artifact, ("bin_width_GeV", "bin_width_gev", "bin_width"))
        if width is None:
            edges = _get_any_field(artifact, FIELD_ALIASES["bin_edges"], [])
            width = round(float(edges[1]) - float(edges[0]), 8) if isinstance(edges, list) and len(edges) >= 2 else None
        evidence["actual_bin_width"] = width
        checks.append(
            isinstance(width, (int, float))
            and float(width_range[0]) <= float(width) <= float(width_range[1])
        )
    min_bins = spec.get("min_bins")
    if min_bins is not None:
        counts = _get_any_field(artifact, FIELD_ALIASES["bin_counts"], [])
        n_bins = len(counts) if isinstance(counts, list) else None
        evidence["n_bins"] = n_bins
        checks.append(isinstance(n_bins, int) and n_bins >= int(min_bins))
    return (1.0 if checks and all(checks) else 0.0, evidence)


def _score_stage_families_present(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    required = spec.get("required_families", [])
    families = _stage_families(trace)
    missing = [family for family in required if not _has_family(families, family)]
    return (1.0 if not missing else 0.0, {"families": families, "missing": missing})


def _score_stage_family_order(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    ordered = spec.get("ordered_families", [])
    families = _stage_families(trace)
    positions: list[int] = []
    missing: list[str] = []
    for required in ordered:
        match_positions = [idx for idx, actual in enumerate(families) if _family_matches(actual, required)]
        if not match_positions:
            missing.append(required)
        else:
            positions.append(match_positions[0])
    ok = not missing and positions == sorted(positions)
    return (1.0 if ok else 0.0, {"families": families, "missing": missing, "positions": positions})


def _score_required_trace_fields(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    fields = spec.get("fields", spec.get("required_fields", []))
    missing = [field for field in fields if _get_path(trace, field) is None]
    return (1.0 if not missing else 0.0, {"missing": missing})


def _score_selection_evidence(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    text = _coerce_text(trace).lower()
    detector_region_evidence = (
        "eta" in text
        and any(token in text for token in ("veto", "transition", "crack", "exclude", "barrel", "endcap", "calorimeter"))
    )
    photon_multiplicity_evidence = (
        "photon" in text
        and any(token in text for token in ("multiplicity", "count", "at_least", "at least", "minimum", ">= 2", "two"))
    )
    requirements = {
        "photon_multiplicity": photon_multiplicity_evidence,
        "quality": not spec.get("requires_photon_quality_or_equivalent") or any(token in text for token in ("tight", "quality", "identification", "istightid")),
        "kinematic": not spec.get("requires_kinematic_reasonableness") or any(token in text for token in ("pt", "kinematic", "momentum")),
        "isolation": not spec.get("requires_isolation_fraction_or_equivalent") or "isolation" in text or "ptcone" in text,
        "eta_veto": not spec.get("requires_eta_transition_veto_or_equivalent") or detector_region_evidence,
    }
    if spec.get("requires_minimum_photon_multiplicity"):
        requirements["minimum_photon_count"] = str(spec["requires_minimum_photon_multiplicity"]) in text or "two" in text
    missing = [name for name, ok in requirements.items() if not ok]
    return (1.0 if not missing else 0.0, {"missing": missing})


def _score_mass_dependent_selection(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    text = _coerce_text(trace).lower()
    compact = re.sub(r"[\s\-]+", "_", text)
    ratio_evidence = any(
        token in compact
        for token in (
            "pt_over",
            "over_mass",
            "over_m_yy",
            "pt/m",
            "pt/m_yy",
            "pt/mgg",
            "pt/mass",
            "mass_scaled",
        )
    )
    explicit_nonzero_evidence = any(
        token in compact
        for token in (
            "nonzero",
            "non_zero",
            "!=_0",
            ">_0",
            "positive_mass",
            "positive_m_yy",
        )
    )
    positive_mass_window = _positive_mass_range_evidence(trace)
    requirements = {
        "mass_before_scaled_cut": not spec.get("requires_mass_computed_before_mass_scaled_cut")
        or (ratio_evidence and ("mass" in text or "m_yy" in text or "mgg" in text)),
        "mass_nonzero": not spec.get("requires_mass_nonzero_handling")
        or explicit_nonzero_evidence
        or (ratio_evidence and positive_mass_window),
        "pt_over_mass": not spec.get("requires_pt_over_mass_requirement_or_equivalent") or ratio_evidence,
    }
    missing = [name for name, ok in requirements.items() if not ok]
    return (
        1.0 if not missing else 0.0,
        {
            "missing": missing,
            "ratio_evidence": ratio_evidence,
            "explicit_nonzero_evidence": explicit_nonzero_evidence,
            "positive_mass_window": positive_mass_window,
        },
    )


def _score_observable_construction(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    text = _coerce_text(trace).lower()
    names = spec.get("observable_name_any_of") or ([spec.get("name")] if spec.get("name") else [])
    inputs = spec.get("required_inputs", spec.get("inputs", []))
    checks = {
        "name": not names or any(str(name).lower() in text for name in names),
        "inputs": all(str(value).lower() in text for value in inputs),
        "mass": "mass" in text or "invariant" in text,
    }
    missing = [name for name, ok in checks.items() if not ok]
    return (1.0 if not missing else 0.0, {"missing": missing})


def _score_inference_method(spec: dict[str, Any], trace: dict[str, Any], artifacts: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    text = (_coerce_text(trace) + " " + _coerce_text(artifacts)).lower()
    accepted = spec.get("acceptable_any_of") or spec.get("scientifically_valid_method_any_of") or []
    if accepted:
        ok = any(_contains_all_tokens(text, str(option).replace("_", " ").split()) for option in accepted)
    else:
        ok = any(token in text for token in ("fit", "background", "signal", "likelihood", "sideband"))
    return (1.0 if ok else 0.0, {"accepted_any_of": accepted})


def _score_data_scope(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    text = _coerce_text(trace).lower()
    required = spec.get("required_dataset", spec)
    periods = required.get("periods", spec.get("required_periods", [])) if isinstance(required, dict) else []
    sample = required.get("sample") if isinstance(required, dict) else spec.get("sample")
    normalized_periods = _period_keys_from_trace(trace)
    missing = []
    if sample and str(sample).lower() not in text:
        missing.append(f"sample:{sample}")
    for period in periods:
        raw = str(period).lower()
        normalized = _period_key(str(period)) or raw.replace("-", "_")
        if raw not in text and normalized not in normalized_periods:
            missing.append(str(period))
    return (
        1.0 if not missing else 0.0,
        {"missing": missing, "normalized_periods": sorted(normalized_periods)},
    )


def _score_validation_evidence(spec: dict[str, Any], submission_dir: Path, trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    optional_files = spec.get("optional_files_any", [])
    existing = [filename for filename in optional_files if (submission_dir / filename).exists()]
    trace_text = _coerce_text(trace).lower()
    labels = spec.get("trace_stage_families_any_labels", spec.get("allowed_validation_types", []))
    matching_labels = [label for label in labels if str(label).replace("_", " ").lower() in trace_text or str(label).lower() in trace_text]
    min_count = int(spec.get("minimum_count", 1))
    count = len(existing) + len(matching_labels)
    if spec.get("requires_result_record") and ("validation" in trace_text or "robust" in trace_text or "stability" in trace_text):
        count += 1
    return (1.0 if count >= min_count else 0.0, {"existing_files": existing, "matching_labels": matching_labels, "count": count})


def _residual_points(artifact: Any) -> list[tuple[float, float]]:
    if not isinstance(artifact, dict):
        return []
    x_values = _get_any_field(artifact, FIELD_ALIASES["bin_centers"], [])
    if not isinstance(x_values, list) or not x_values:
        edges = _get_any_field(artifact, FIELD_ALIASES["bin_edges"], [])
        if isinstance(edges, list) and len(edges) >= 2:
            x_values = [
                0.5 * (float(lo) + float(hi))
                for lo, hi in zip(edges[:-1], edges[1:])
                if isinstance(lo, (int, float)) and isinstance(hi, (int, float))
            ]
    y_values = _get_any_field(artifact, FIELD_ALIASES["residual_counts"], [])
    if not isinstance(x_values, list) or not isinstance(y_values, list) or len(x_values) != len(y_values):
        return []
    return [
        (float(x), float(y))
        for x, y in zip(x_values, y_values)
        if isinstance(x, (int, float)) and isinstance(y, (int, float))
    ]


def _score_residual_excess(spec: dict[str, Any], artifacts: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    filename = spec.get("file")
    roi = spec.get("roi_gev", spec.get("region_of_interest_gev", [None, None]))
    if not isinstance(filename, str) or not isinstance(roi, list) or len(roi) != 2:
        return (0.0, {"reason": "invalid_residual_spec"})
    points = _residual_points(artifacts.get(filename, {}))
    roi_points = [(x, y) for x, y in points if float(roi[0]) <= x <= float(roi[1])]
    if not roi_points:
        return (0.0, {"reason": "no_points_in_roi"})
    peak_x, peak_y = max(roi_points, key=lambda item: item[1])
    ok = peak_y > 0
    return (1.0 if ok else 0.0, {"peak_x": peak_x, "peak_y": peak_y})


def _score_cross_artifact_consistency(spec: dict[str, Any], artifacts: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    fit_spec = {
        "file": spec.get("fit_summary_file"),
        "field": spec.get("fit_peak_field", "gaussian_mean_gev"),
        "expected_range": spec.get("fit_peak_expected_range"),
    }
    fit_score, fit_evidence = _score_numeric_range(fit_spec, artifacts)
    residual_spec = {
        "file": spec.get("residual_file"),
        "region_of_interest_gev": spec.get("residual_roi_gev"),
    }
    residual_score, residual_evidence = _score_residual_excess(residual_spec, artifacts)
    ok = fit_score > 0 and residual_score > 0
    return (1.0 if ok else 0.0, {"fit": fit_evidence, "residual": residual_evidence})


def _score_deterministic(
    condition: Dict[str, Any],
    submission_dir: Path,
    trace: Dict[str, Any],
    artifacts: Dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    if "required_outputs" in condition:
        files = [entry["canonical_filename"] for entry in condition["required_outputs"] if isinstance(entry, dict)]
        return _score_required_files(files, submission_dir)
    if "required_files" in condition:
        return _score_required_files([str(name) for name in condition["required_files"]], submission_dir)
    if "files_nonempty" in condition:
        return _score_files_nonempty([str(name) for name in condition["files_nonempty"]], submission_dir)

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
                    failures.append({"cut_id": expected["cut_id"], "field": key, "expected": value, "actual": actual.get(key)})
                    break
        return (1.0 if not failures else 0.0, {"failures": failures})

    if "selection_constraints" in condition:
        return _score_selection_evidence(condition["selection_constraints"], trace)

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
        return _score_numeric_range(
            {
                "file": condition["artifact_id"],
                "field": condition["field"],
                "expected_range": condition["expected_range"],
            },
            artifacts,
        )
    if "artifact_numeric_field_range" in condition:
        return _score_numeric_range(condition["artifact_numeric_field_range"], artifacts)
    if "artifact_value_in_range" in condition:
        return _score_numeric_range(condition["artifact_value_in_range"], artifacts)
    if "artifact_histogram_properties" in condition:
        return _score_histogram_properties(condition["artifact_histogram_properties"], artifacts)
    if "artifact_field_constraints" in condition:
        spec = condition["artifact_field_constraints"]
        return (1.0 if artifacts.get(spec.get("file")) else 0.0, {"checked": "artifact_field_constraints"})
    if "observable_match" in condition:
        return _score_observable_construction(condition["observable_match"], trace)

    return (0.0, {"reason": "unsupported_deterministic_condition"})


def _score_structural(
    condition: Dict[str, Any],
    submission_dir: Path,
    trace: Dict[str, Any],
    artifacts: Dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
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

    if "files_nonempty" in condition:
        return _score_files_nonempty([str(name) for name in condition["files_nonempty"]], submission_dir)
    if "trace_required_fields" in condition:
        return _score_required_trace_fields(condition["trace_required_fields"], trace)
    if "trace_stage_families_present" in condition:
        return _score_stage_families_present(condition["trace_stage_families_present"], trace)
    if "trace_stage_family_order" in condition:
        return _score_stage_family_order(condition["trace_stage_family_order"], trace)
    if "scientifically_valid_selection_evidence" in condition:
        return _score_selection_evidence(condition["scientifically_valid_selection_evidence"], trace)
    if "trace_mass_dependent_selection" in condition:
        return _score_mass_dependent_selection(condition["trace_mass_dependent_selection"], trace)
    if "trace_observable_construction" in condition:
        return _score_observable_construction(condition["trace_observable_construction"], trace)
    if "inference_method_acceptable" in condition:
        return _score_inference_method(condition["inference_method_acceptable"], trace, artifacts)
    if "scientifically_valid_method_any_of" in condition:
        return _score_inference_method(condition, trace, artifacts)
    if "trace_data_scope_coverage" in condition:
        return _score_data_scope(condition["trace_data_scope_coverage"], trace)
    if "data_scope_coverage" in condition:
        return _score_data_scope(condition["data_scope_coverage"], trace)
    if "workflow_evidence_present" in condition:
        return _score_stage_families_present(
            {"required_families": ["data_access", "selection", "observable_construction", "spectrum_construction", "inference_or_signal_localization", "interpretation"]},
            trace,
        )
    if "workflow_partial_order" in condition:
        constraints = condition["workflow_partial_order"].get("order_constraints", [])
        ordered = []
        for item in constraints:
            if isinstance(item, dict):
                earlier = item.get("earlier", (item.get("earlier_any_of") or [None])[0])
                later = item.get("later", (item.get("later_any_of") or [None])[0])
                if earlier and later:
                    ordered.extend([earlier, later])
        return _score_stage_family_order({"ordered_families": ordered}, trace)
    if "validation_evidence_any" in condition:
        return _score_validation_evidence(condition["validation_evidence_any"], submission_dir, trace)

    return (0.0, {"reason": "unsupported_structural_condition"})


def _score_heuristic(
    condition: Dict[str, Any],
    submission_dir: Path,
    trace: Dict[str, Any],
    artifacts: Dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    if "localized_excess_in_residual" in condition:
        return _score_residual_excess(condition["localized_excess_in_residual"], artifacts)
    if "residual_signal_region_check" in condition:
        return _score_residual_excess(condition["residual_signal_region_check"], artifacts)
    if "cross_artifact_region_consistency" in condition:
        return _score_cross_artifact_consistency(condition["cross_artifact_region_consistency"], artifacts)
    if "model_data_coherence" in condition:
        files = condition["model_data_coherence"].get("files", {})
        missing = [name for name in files.values() if not artifacts.get(name)]
        return (1.0 if not missing else 0.0, {"missing": missing})
    if "validation_targets_signal_inference" in condition:
        text = _coerce_text(trace).lower()
        ok = "125" in text or "signal" in text or "excess" in text
        return (1.0 if ok else 0.0, {"has_signal_evidence": ok})

    artifact = artifacts.get(condition.get("artifact_id", ""), {})
    x_values = _get_any_field(artifact, [condition.get("x_field", "")], [])
    y_values = _get_any_field(artifact, [condition.get("y_field", "")], [])
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
    artifacts: Dict[str, Any],
    interpretation: str,
    judge: Optional[BaseJudge],
) -> Tuple[float, Dict[str, Any]]:
    if judge is None:
        return (0.0, {"reason": "judge_unavailable"})

    evidence = {
        "submission_trace": trace,
        "interpretation": interpretation,
        "artifacts": artifacts,
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
        {"evidence": evidence, "judge_rubric": condition.get("judge_rubric", condition.get("rubric", condition))},
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


def _interpretation_text(artifacts: dict[str, Any], submission_dir: Path) -> str:
    for key in ("interpretation", "interpretation.md"):
        value = artifacts.get(key)
        if isinstance(value, str):
            return value
    return _load_text_if_exists(submission_dir / "interpretation.md")


def score_submission(
    task: Any,
    submission_dir: Path,
    rubric: Dict[str, Any],
    contract_report: Dict[str, Any],
    *,
    judge: Optional[BaseJudge] = None,
) -> Dict[str, Any]:
    contract = load_submission_contract(task)
    trace = _load_json_if_exists(submission_dir / "submission_trace.json")
    trace = trace if isinstance(trace, dict) else {}
    artifacts = _load_artifacts(submission_dir, contract)
    interpretation = _interpretation_text(artifacts, submission_dir)

    dimension_scores: Dict[str, float] = {
        dimension: 0.0 for dimension in expected_dimensions(task, rubric)
    }
    check_results: List[Dict[str, Any]] = []
    weights = rubric.get("weights", {}) or {}

    for dimension, checks in (rubric.get("checks", {}) or {}).items():
        if dimension == "validation" and float(weights.get("validation", 0.0)) == 0.0:
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
                achieved, evidence = _score_structural(condition, submission_dir, trace, artifacts)
            elif ctype == "heuristic":
                achieved, evidence = _score_heuristic(condition, submission_dir, trace, artifacts)
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
