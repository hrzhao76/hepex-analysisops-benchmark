from __future__ import annotations

import json
import math
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
    "data_access": ("data", "load", "read", "input", "access", "download", "manifest", "sample", "file"),
    "data_loading": ("data", "load", "read", "input", "access", "download", "manifest", "sample", "file"),
    "event_weighting": (
        "weight",
        "weighted",
        "weighting",
        "normalization",
        "normalisation",
        "normalised",
        "normalized",
        "luminosity",
        "mcweight",
        "scale factor",
        "scalefactor",
        "xsec",
        "kfac",
        "filteff",
        "sum_of_weights",
    ),
    "mc_weighting": (
        "weight",
        "weighted",
        "weighting",
        "normalization",
        "normalisation",
        "normalised",
        "normalized",
        "luminosity",
        "mcweight",
        "scale factor",
        "scalefactor",
        "xsec",
        "kfac",
        "filteff",
        "sum_of_weights",
    ),
    "object_or_event_selection": ("select", "selection", "cut", "filter", "photon", "lepton", "candidate", "quality", "isolation"),
    "selection": ("select", "selection", "cut", "filter", "photon", "lepton", "candidate", "quality", "isolation"),
    "observable_construction": ("observable", "mass", "construct", "invariant", "m_yy", "mgg", "m4l", "m_4l", "reconstruct"),
    "mass_construction_or_signal_proxy": ("observable", "mass", "construct", "invariant", "m_yy", "mgg", "m4l", "m_4l", "proxy", "reconstruct"),
    "spectrum_or_summary_construction": ("histogram", "spectrum", "bin", "binned", "summary", "counts", "yield"),
    "spectrum_construction": ("histogram", "spectrum", "bin", "binned", "counts", "yield"),
    "inference_or_signal_localization": (
        "fit",
        "inference",
        "signal",
        "local",
        "localized",
        "background model",
        "background comparison",
        "likelihood",
        "counting",
        "window",
        "excess",
        "assessment",
        "comparison",
    ),
    "signal_extraction": ("fit", "inference", "signal", "extract", "likelihood", "counting", "window", "excess"),
    "residual_or_background_subtraction": (
        "residual",
        "subtract",
        "minus",
        "data_minus_background",
        "background subtract",
        "background-subtracted",
    ),
    "interpretation": ("interpret", "interpretation", "conclusion", "claim", "report", "result"),
    "validation": ("validate", "validation", "robust", "stability", "cross", "scan", "sideband", "alternative", "check", "sanity"),
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
    "event_weighting": "event_weighting",
    "mc_weighting": "event_weighting",
    "mc_event_weighting": "event_weighting",
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
    "bin_counts": ("bin_counts", "counts", "data_counts", "background_counts", "signal_counts"),
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


def _normalize_operator(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return {"in_set": "in", "is_in": "in"}.get(normalized, normalized)


def _compact_expr(value: str) -> str:
    return re.sub(r"[^a-z0-9_\[\]:+*/<>=!]+", "", value.lower())


def _normalize_formula_key(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().lower()
    compact = _compact_expr(text)
    alias = {
        "data_minus_background_over_sqrt_background": "data_minus_background_over_sqrt_background",
        "n_obsn_bkg/sqrtn_bkg": "data_minus_background_over_sqrt_background",
        "nobsnbkg/sqrtnbkg": "data_minus_background_over_sqrt_background",
        "obsbkg/sqrtbkg": "data_minus_background_over_sqrt_background",
        "numerator_minus_background_over_sqrt_background": "numerator_minus_background_over_sqrt_background",
        "signal_over_sqrt_background": "signal_over_sqrt_background",
        "data_minus_background_over_sqrt_background_plus_variance": "data_minus_background_over_sqrt_background_plus_variance",
        "numerator_over_sqrt_background_plus_fractional_systematic": "numerator_over_sqrt_background_plus_fractional_systematic",
        "background_plus_signal_over_sqrt_background_plus_fractional_systematic": "background_plus_signal_over_sqrt_background_plus_fractional_systematic",
        "bpluss_over_sqrt_b_plus_frac_b2": "background_plus_signal_over_sqrt_background_plus_fractional_systematic",
    }
    if compact in alias:
        return alias[compact]
    if "sqrt" in compact and (
        "sum_iw_i2" in compact or "sum_iw_i^2" in compact or "sumw2" in compact or "sumw^2" in compact or "variance" in compact
    ):
        if (
            ("data" in compact or "obs" in compact or "observed" in compact or "n_obs" in compact or "nobs" in compact)
            and ("background" in compact or "bkg" in compact or "n_bkg" in compact or "nbkg" in compact)
            and ("minus" in compact or "-" in text)
        ):
            return "data_minus_background_over_sqrt_background_plus_variance"
    if "sqrt" in compact and ("0.3" in text or "fractional" in text or "systematic" in text):
        if "backgroundplussignal" in compact or "b+s" in text or "numerator" in compact:
            return "numerator_over_sqrt_background_plus_fractional_systematic"
    if "sqrt" in compact and "signal" in compact and "background" in compact:
        return "signal_over_sqrt_background"
    if (
        "sqrt" in compact
        and ("data" in compact or "obs" in compact or "observed" in compact or "n_obs" in compact or "nobs" in compact)
        and ("background" in compact or "bkg" in compact or "n_bkg" in compact or "nbkg" in compact)
        and ("minus" in compact or "-" in text)
    ):
        return "data_minus_background_over_sqrt_background"
    if "sqrt" in compact and "numerator" in compact and "background" in compact and ("minus" in compact or "-" in text):
        return "numerator_minus_background_over_sqrt_background"
    return compact


def _selection_variable_aliases(value: Any) -> set[str]:
    if not isinstance(value, str):
        return set()

    compact = _compact_expr(value)
    aliases = {compact}
    canonical_tokens = (
        "event_trigger_pass",
        "trigger_matched_lepton_count",
        "typed_quality_lepton_count",
        "sum_lep_type",
        "total_lepton_charge",
        "leading_lep_pt",
        "sub_leading_lep_pt",
        "third_leading_lep_pt",
    )
    for token in canonical_tokens:
        if _compact_expr(token) in compact:
            aliases.add(token)

    if "trige" in compact and "trigm" in compact:
        aliases.add("event_trigger_pass")
    if "lep_istrigmatched" in compact and ("sum" in compact or "count" in compact):
        aliases.add("trigger_matched_lepton_count")
    if "lep_pt[0]" in compact:
        aliases.add("leading_lep_pt")
    if "lep_pt[1]" in compact:
        aliases.add("sub_leading_lep_pt")
    if "lep_pt[2]" in compact:
        aliases.add("third_leading_lep_pt")
    if "lep_type[0:4]" in compact or all(f"lep_type[{idx}]" in compact for idx in range(4)):
        aliases.add("sum_lep_type")
    if "lep_charge[0:4]" in compact or all(f"lep_charge[{idx}]" in compact for idx in range(4)):
        aliases.add("total_lepton_charge")

    has_explicit_typed_quality = all(
        token in compact
        for token in ("lep_type==13", "lep_ismediumid", "lep_islooseiso", "lep_type==11", "lep_islooseid")
    )
    has_descriptive_typed_quality = all(token in compact for token in ("mu", "medium", "looseiso", "looseid"))
    if has_explicit_typed_quality or has_descriptive_typed_quality:
        aliases.add("typed_quality_lepton_count")

    return aliases


def _selection_variable_matches(actual_value: Any, expected_value: Any) -> bool:
    if _match_subset(actual_value, expected_value):
        return True
    actual_aliases = _selection_variable_aliases(actual_value)
    expected_aliases = _selection_variable_aliases(expected_value)
    return bool(actual_aliases and expected_aliases and actual_aliases.intersection(expected_aliases))


def _selection_field_matches(actual: dict[str, Any], expected_key: str, expected_value: Any) -> bool:
    if expected_key.endswith("_any_of"):
        actual_key = expected_key.removesuffix("_any_of")
        options = expected_value if isinstance(expected_value, list) else [expected_value]
        return any(_selection_field_matches(actual, actual_key, option) for option in options)

    actual_value = actual.get(expected_key)
    if expected_key == "operator":
        return _normalize_operator(actual_value) == _normalize_operator(expected_value)
    if expected_key == "variable":
        return _selection_variable_matches(actual_value, expected_value)
    return _match_subset(actual_value, expected_value)


def _contains_all_tokens(text: str, tokens: list[str]) -> bool:
    normalized = text.lower()
    return all(token.lower() in normalized for token in tokens)


def _normalize_family(value: str) -> str:
    return FAMILY_ALIASES.get(value, value)


def _stage_families_for_text(text: str) -> list[str]:
    normalized = text.lower()
    compact = _compact_expr(normalized)
    families: list[str] = []
    for family, keywords in FAMILY_KEYWORDS.items():
        if any(keyword in normalized or _compact_expr(keyword) in compact for keyword in keywords):
            normalized_family = _normalize_family(family)
            if normalized_family not in families:
                families.append(normalized_family)
    return families


def _explicit_stage_families(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_normalize_family(value)]
    if isinstance(value, list):
        families: list[str] = []
        for item in value:
            if isinstance(item, str):
                family = _normalize_family(item)
                if family not in families:
                    families.append(family)
        return families
    return []


def _trace_family_observations(trace: dict[str, Any], *, include_supplemental: bool = True) -> list[tuple[str, float, str]]:
    observations: list[tuple[str, float, str]] = []
    for index, entry in enumerate(_stage_entries(trace)):
        text = " ".join(
            str(entry.get(key, ""))
            for key in ("stage_id", "stage_label", "role", "description", "family", "stage_family")
        )
        families = _explicit_stage_families(entry.get("family") or entry.get("stage_family"))
        for family in _stage_families_for_text(text):
            if family not in families:
                families.append(family)
        for family in families:
            observations.append((family, float(index), "workflow_stages"))

    if not include_supplemental:
        return observations

    supplemental_fields = (
        "scientific_decisions",
        "selection_strategy",
        "cuts_applied",
        "observable_constructed",
        "primary_observable",
        "histogram_definition",
        "inference_strategy",
        "fit_model_family_used",
        "validation_checks",
        "validation_actions",
        "output_files_generated",
    )
    base_index = float(len(_stage_entries(trace)))
    for offset, field in enumerate(supplemental_fields):
        value = trace.get(field)
        if value is None:
            continue
        text = f"{field} {_coerce_text(value)}"
        for family in _stage_families_for_text(text):
            observations.append((family, base_index + (offset + 1) / 100.0, field))

    return observations


def _stage_families(trace: dict[str, Any]) -> list[str]:
    families: list[str] = []
    for family, _, _ in _trace_family_observations(trace):
        families.append(family)
    return families


def _family_matches(actual: str, required: str) -> bool:
    actual_norm = _normalize_family(actual)
    required_norm = _normalize_family(required)
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
    matched = len(required) - len(missing)
    fraction = 1.0 if not required else matched / len(required)
    minimum = spec.get("minimum_pass_fraction")
    if minimum is not None:
        achieved = fraction if spec.get("partial_credit") else (1.0 if fraction >= float(minimum) else 0.0)
    else:
        achieved = 1.0 if not missing else 0.0
    return (
        achieved,
        {
            "families": families,
            "missing": missing,
            "matched": matched,
            "required": len(required),
            "match_fraction": fraction,
        },
    )


def _score_stage_family_order(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    observations = _trace_family_observations(trace, include_supplemental=False)
    families = [family for family, _, _ in observations]
    family_positions = {
        required: [position for actual, position, _ in observations if _family_matches(actual, required)]
        for required in set(spec.get("ordered_families", []))
    }
    ignore_missing = bool(spec.get("ignore_missing_families"))
    allow_same_stage = bool(spec.get("allow_same_stage", True))
    partial_orders = spec.get("required_partial_orders")
    if isinstance(partial_orders, list):
        failed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for entry in partial_orders:
            if not isinstance(entry, dict):
                continue
            before = entry.get("before") or entry.get("earlier")
            after = entry.get("after") or entry.get("later")
            if not isinstance(before, str) or not isinstance(after, str):
                continue
            before_positions = [position for actual, position, _ in observations if _family_matches(actual, before)]
            after_positions = [position for actual, position, _ in observations if _family_matches(actual, after)]
            if not before_positions or not after_positions:
                if ignore_missing:
                    skipped.append({"before": before, "after": after, "reason": "missing_family"})
                    continue
                failed.append({"before": before, "after": after})
                continue
            ordered = min(before_positions) <= max(after_positions) if allow_same_stage else min(before_positions) < max(after_positions)
            if not ordered:
                failed.append({"before": before, "after": after})
        if spec.get("minimum_pass_fraction") is not None:
            total = len([entry for entry in partial_orders if isinstance(entry, dict)])
            passed = total - len(failed) - (0 if ignore_missing else len(skipped))
            fraction = 1.0 if total == 0 else passed / total
            achieved = fraction if spec.get("partial_credit") else (1.0 if fraction >= float(spec["minimum_pass_fraction"]) else 0.0)
        else:
            achieved = 1.0 if not failed else 0.0
        return (
            achieved,
            {
                "families": families,
                "failed_orders": failed,
                "skipped_orders": skipped,
            },
        )

    ordered = spec.get("ordered_families", [])
    positions: list[int] = []
    missing: list[str] = []
    for required in ordered:
        match_positions = family_positions.get(required, [])
        if not match_positions:
            missing.append(required)
        else:
            positions.append(match_positions[0])
    ok = (not missing or ignore_missing) and positions == sorted(positions)
    return (1.0 if ok else 0.0, {"families": families, "missing": missing, "positions": positions})


def _score_required_trace_fields(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    fields = spec.get("fields", spec.get("required_fields", []))
    missing = [field for field in fields if _get_path(trace, field) is None]
    return (1.0 if not missing else 0.0, {"missing": missing})


def _score_selection_evidence(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    text = _coerce_text(trace).lower()
    compact = _compact_expr(text)
    default_component_groups = {
        "trigger": ("trigger", "trig"),
        "trigger_matching": ("trigger matched", "trigger_matched", "istrigmatched", "triggermatched", "trigger-compatible"),
        "kinematic": ("pt", "p_t", "threshold", "kinematic", "momentum", "leading", "subleading", "ordered"),
        "object_quality": ("quality", "identification", "id", "tight", "looseid", "mediumid", "electron", "muon", "photon"),
        "isolation": ("isolation", "iso", "ptcone", "looseiso"),
        "topology": ("4e", "2e2mu", "4mu", "flavour", "flavor", "channel", "quadruplet", "four lepton", "diphoton", "two photon", "exactly4lep"),
        "charge": ("charge", "zero", "neutral", "total_charge", "net charge", "==0"),
        "multiplicity": ("at least", "minimum", "multiplicity", "count", "two", "four", ">=2", ">= 2", "exactly4lep"),
        "detector_region": ("eta", "veto", "transition", "crack", "barrel", "endcap", "calorimeter"),
    }
    required_groups = spec.get("required_component_groups")
    if isinstance(required_groups, list) and required_groups:
        custom_groups = spec.get("component_groups", {})
        group_tokens: dict[str, tuple[str, ...]] = dict(default_component_groups)
        if isinstance(custom_groups, dict):
            for name, tokens in custom_groups.items():
                if isinstance(name, str):
                    values = tokens if isinstance(tokens, list) else [tokens]
                    group_tokens[name] = tuple(str(value) for value in values)
        present: list[str] = []
        missing: list[str] = []
        for group in [str(value) for value in required_groups]:
            tokens = group_tokens.get(group, (group.replace("_", " "),))
            found = any(token.lower() in text or _compact_expr(token) in compact for token in tokens)
            if found:
                present.append(group)
            else:
                missing.append(group)
        minimum = int(spec.get("minimum_groups", len(required_groups)))
        achieved = 1.0 if len(present) >= minimum else 0.0
        if spec.get("partial_credit"):
            achieved = len(present) / len(required_groups)
        return (
            achieved,
            {
                "present": present,
                "missing": missing,
                "minimum_groups": minimum,
            },
        )

    required_components = spec.get("required_components")
    if isinstance(required_components, list) and required_components:
        component_tokens = {
            "trigger_requirement": ("trigger", "trig"),
            "at_least_one_trigger_matched_lepton": ("trigger_matched", "istrigmatched", "triggermatched", "trigger match", "trigger-compatible"),
            "hierarchical_pt_requirement_on_first_three_leptons": ("lep_pt[0]", "lep_pt[1]", "lep_pt[2]", "leading", "subleading", "third", "ordered pt", "p_t threshold"),
            "flavour_dependent_identification": ("looseid", "mediumid", "tightid", "tight id", "tight-id", "identification", "flavour", "flavor", "electron", "muon"),
            "loose_isolation": ("looseiso", "isolation", "iso"),
            "allowed_four_lepton_flavour_channels": ("4e", "2e2mu", "4mu", "44", "48", "52", "flavour", "flavor", "exactly4lep", "four lepton"),
            "total_charge_zero": ("charge", "zero", "==0"),
        }
        missing = []
        for component in required_components:
            tokens = component_tokens.get(str(component), (str(component).replace("_", " "),))
            if not any(_compact_expr(token) in compact for token in tokens):
                missing.append(str(component))
        minimum = spec.get("minimum_components")
        if minimum is not None:
            present_count = len(required_components) - len(missing)
            achieved = 1.0 if present_count >= int(minimum) else 0.0
        else:
            achieved = 1.0 if not missing else 0.0
        return (achieved, {"missing": missing})

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
    if spec.get("semantic_id") == "four_lepton_invariant_mass":
        names = list(names) + ["four_lepton", "four lepton", "m4l", "m_4l", "mass"]
    inputs = spec.get("required_inputs", spec.get("inputs_must_include", spec.get("inputs", [])))
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


def _normalize_ref(value: str) -> str:
    return value.strip().strip(".,;:)]}\"'")


def _root_refs_from_trace(trace: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for value in _all_strings(trace):
        for match in re.findall(r"https?://[^\s\"']+?\.root|/[^\s\"']+?\.root|[A-Za-z0-9_.+-]+\.root", value):
            refs.add(_normalize_ref(match))
    return refs


def _manifest_allowed_refs(manifest: dict[str, Any]) -> set[str]:
    refs: set[str] = set()
    for entry in manifest.get("files", []) or []:
        if not isinstance(entry, dict):
            continue
        for key in ("logical_name", "path", "source"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                refs.add(value)
                refs.add(Path(value).name)
    return refs


def _ref_is_allowed(ref: str, allowed_refs: set[str]) -> bool:
    normalized = _normalize_ref(ref)
    basename = Path(normalized).name
    return normalized in allowed_refs or basename in allowed_refs


def _score_hzz_sample_manifest_coverage(
    spec: dict[str, Any],
    submission_dir: Path,
    trace: dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    manifest_file = spec.get("input_manifest_file", "input_manifest.json")
    manifest = _load_json_if_exists(submission_dir / str(manifest_file))
    if not isinstance(manifest, dict):
        return (0.0, {"reason": "missing_multi_sample_manifest", "manifest_file": manifest_file})
    manifest_samples = manifest.get("samples")
    if not isinstance(manifest_samples, list):
        manifest_samples = manifest.get("sample_groups")
    if not isinstance(manifest_samples, list):
        return (0.0, {"reason": "missing_multi_sample_manifest", "manifest_file": manifest_file})

    required_sample_names = spec.get("required_sample_names") or []
    required_sample_ids = spec.get("required_sample_ids") or spec.get("required_sample_group_ids") or [
        sample.get("id") for sample in manifest_samples if isinstance(sample, dict)
    ]
    required_sample_names = [str(name) for name in required_sample_names if name]
    required_sample_ids = [str(sample_id) for sample_id in required_sample_ids if sample_id]

    trace_text = _coerce_text(trace).lower()
    trace_refs = _root_refs_from_trace(trace)
    allowed_refs = _manifest_allowed_refs(manifest)
    off_manifest_refs = sorted(ref for ref in trace_refs if not _ref_is_allowed(ref, allowed_refs))

    files_by_sample_id: dict[str, list[dict[str, Any]]] = {}
    files_by_sample_name: dict[str, list[dict[str, Any]]] = {}
    for entry in manifest.get("files", []) or []:
        if not isinstance(entry, dict):
            continue
        sample_id = entry.get("sample_id") or entry.get("sample_group_id")
        sample_name = entry.get("sample_name") or entry.get("sample_group_label")
        if isinstance(sample_id, str):
            files_by_sample_id.setdefault(sample_id, []).append(entry)
        if isinstance(sample_name, str):
            files_by_sample_name.setdefault(sample_name, []).append(entry)

    samples_by_id = {
        sample.get("id"): sample
        for sample in manifest_samples
        if isinstance(sample, dict) and isinstance(sample.get("id"), str)
    }
    samples_by_name = {
        (sample.get("name") or sample.get("label")): sample
        for sample in manifest_samples
        if isinstance(sample, dict) and isinstance(sample.get("name") or sample.get("label"), str)
    }

    missing_samples: list[str] = []
    required_samples: list[tuple[str, str]] = [("id", sample_id) for sample_id in required_sample_ids]
    required_samples.extend(("name", name) for name in required_sample_names)
    for kind, required in required_samples:
        sample = samples_by_id.get(required, {}) if kind == "id" else samples_by_name.get(required, {})
        sample_name = str(sample.get("name") or sample.get("label") or "")
        sample_id = str(sample.get("id") or "")
        labels = [required, sample_id, sample_name, str(sample.get("role", ""))]
        mentioned = any(label and label.lower() in trace_text for label in labels)
        if not mentioned:
            candidate_files = files_by_sample_id.get(required, []) if kind == "id" else files_by_sample_name.get(required, [])
            for entry in candidate_files:
                refs = [entry.get("logical_name"), entry.get("path"), entry.get("source")]
                if any(isinstance(ref, str) and ref and ref.lower() in trace_text for ref in refs):
                    mentioned = True
                    break
        if not mentioned:
            missing_samples.append(required)

    ok = not missing_samples and (not spec.get("reject_off_manifest_root_refs", True) or not off_manifest_refs)
    return (
        1.0 if ok else 0.0,
        {
            "missing_samples": missing_samples,
            "off_manifest_root_refs": off_manifest_refs,
            "manifest_sample_ids": sorted(samples_by_id),
            "manifest_sample_names": sorted(samples_by_name),
            "trace_root_ref_count": len(trace_refs),
        },
    )


def _score_trace_data_assembly_semantics(
    spec: dict[str, Any],
    submission_dir: Path,
    trace: dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    text = _coerce_text(trace).lower()
    manifest = _load_json_if_exists(submission_dir / "input_manifest.json")
    manifest = manifest if isinstance(manifest, dict) else {}
    manifest_text = _coerce_text(manifest).lower()
    combined_text = f"{text} {manifest_text}"

    missing: list[str] = []
    expected_skim = spec.get("expected_skim")
    if isinstance(expected_skim, str) and expected_skim.lower() not in combined_text:
        missing.append(f"skim:{expected_skim}")
    expected_source = spec.get("expected_source")
    if isinstance(expected_source, str):
        source_tokens = [expected_source.lower(), expected_source.replace("_", " ").lower(), "atlas open data"]
        if "atlas" in expected_source.lower():
            source_tokens.extend(["opendata/atlas", "atlas/rucio", "atlas"])
        if not any(token in combined_text for token in source_tokens):
            missing.append(f"source:{expected_source}")

    manifest_roles = {
        entry.get("role")
        for entry in (manifest.get("samples") or manifest.get("sample_groups") or [])
        if isinstance(entry, dict)
    }
    trace_roles = set(re.findall(r"\b(data|background|signal)\b", text))
    present_roles = {str(role) for role in manifest_roles if role} | trace_roles
    for role in spec.get("required_sample_roles", []) or []:
        if str(role) not in present_roles:
            missing.append(f"role:{role}")

    semantic_tokens = {
        "background_combination_mode": ("stack", "sum", "background"),
        "signal_usage_mode": ("signal", "overlay", "template", "reference"),
        "data_usage_mode": ("data", "observed"),
    }
    for key, tokens in semantic_tokens.items():
        if spec.get(key) and not any(token in combined_text for token in tokens):
            missing.append(key)

    return (
        1.0 if not missing else 0.0,
        {"missing": missing, "manifest_roles": sorted(present_roles)},
    )


def _score_mc_weighting_strategy(spec: dict[str, Any], trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    evidence_field = spec.get("required_evidence_field") or spec.get("evidence_field")
    structured_evidence: Any = None
    missing: list[str] = []
    if isinstance(evidence_field, str) and evidence_field:
        structured_evidence = trace.get(evidence_field)
        if not isinstance(structured_evidence, dict):
            reason = f"missing_structured_evidence:{evidence_field}"
            if spec.get("require_structured_evidence", True):
                missing.append(reason)
            structured_evidence = {}
    else:
        structured_evidence = trace.get("mc_weighting_evidence") if isinstance(trace.get("mc_weighting_evidence"), dict) else {}

    weighting_context = {
        "mc_weighting_evidence": structured_evidence,
        "scientific_decisions": trace.get("scientific_decisions"),
        "inference_strategy": trace.get("inference_strategy"),
        "validation_checks": trace.get("validation_checks"),
        "validation_actions": trace.get("validation_actions"),
        "result_summary": trace.get("result_summary"),
        "workflow_stages": trace.get("workflow_stages"),
    }
    text = _coerce_text(weighting_context).lower()
    compact = _compact_expr(text)
    if spec.get("data_policy") == "unweighted" and "unweighted" not in text:
        missing.append("data_policy:unweighted")
    if spec.get("mc_policy") and not any(token in text for token in ("weighted", "weighting", "normaliz", "normalis", "luminosity")):
        missing.append(f"mc_policy:{spec.get('mc_policy')}")
    luminosity = spec.get("luminosity_fb_inv")
    if luminosity is not None:
        lum_text = str(luminosity).rstrip("0").rstrip(".")
        if lum_text not in text:
            missing.append(f"luminosity:{luminosity}")

    factor_aliases = {
        "sum_of_weights": ("sum_of_weights", "sum of weights", "sumweights", "sumw"),
        "mcweight": ("mcweight", "mc weight", "event weight"),
        "xsec": ("xsec", "cross section", "cross-section", "cross_section"),
        "filteff": ("filteff", "filter efficiency", "filter_efficiency"),
        "kfac": ("kfac", "k-factor", "k factor"),
        "scale_factor": ("scale factor", "scale factors", "scalefactor", "scalefactors"),
        "pileup": ("pileup", "pile-up", "scale factor"),
        "electron_scale_factor": ("scalefactor_ele", "scale factor ele", "electron scale factor", "scale factor"),
        "muon_scale_factor": ("scalefactor_muon", "scale factor muon", "muon scale factor", "scale factor"),
        "trigger_scale_factor": ("scalefactor_leptrigger", "trigger scale factor", "leptrigger", "scale factor"),
    }

    def factor_present(raw: str) -> bool:
        key = raw.lower()
        normalized_key = _compact_expr(key)
        aliases = [raw]
        if normalized_key in {"mcweight"}:
            aliases.extend(factor_aliases["mcweight"])
        elif normalized_key in {"sum_of_weights", "sumofweights"}:
            aliases.extend(factor_aliases["sum_of_weights"])
        elif normalized_key in {"xsec"}:
            aliases.extend(factor_aliases["xsec"])
        elif normalized_key in {"filteff"}:
            aliases.extend(factor_aliases["filteff"])
        elif normalized_key in {"kfac"}:
            aliases.extend(factor_aliases["kfac"])
        elif normalized_key.startswith("scalefactor"):
            aliases.extend(factor_aliases["scale_factor"])
            if "pileup" in normalized_key:
                aliases.extend(factor_aliases["pileup"])
            if "ele" in normalized_key:
                aliases.extend(factor_aliases["electron_scale_factor"])
            if "muon" in normalized_key:
                aliases.extend(factor_aliases["muon_scale_factor"])
            if "trigger" in normalized_key:
                aliases.extend(factor_aliases["trigger_scale_factor"])
        return any(alias.lower() in text or _compact_expr(alias) in compact for alias in aliases)

    for factor in spec.get("required_mc_factors", []) or []:
        if not factor_present(str(factor)):
            missing.append(str(factor))

    factor_groups = spec.get("required_factor_groups", [])
    group_tokens = {
        "event_weight": factor_aliases["mcweight"],
        "cross_section": factor_aliases["xsec"],
        "filter_efficiency": factor_aliases["filteff"],
        "k_factor": factor_aliases["kfac"],
        "sum_of_weights": factor_aliases["sum_of_weights"],
        "scale_factors": factor_aliases["scale_factor"],
        "luminosity": ("luminosity", "fb", "fb^-1", "fb-1"),
    }
    present_groups: list[str] = []
    missing_groups: list[str] = []
    if isinstance(factor_groups, list):
        for group in [str(value) for value in factor_groups]:
            tokens = group_tokens.get(group, (group.replace("_", " "),))
            if any(token.lower() in text or _compact_expr(token) in compact for token in tokens):
                present_groups.append(group)
            else:
                missing_groups.append(group)
        minimum_groups = int(spec.get("minimum_factor_groups", len(factor_groups)))
        if len(present_groups) < minimum_groups:
            missing.extend(f"group:{group}" for group in missing_groups)

    return (
        1.0 if not missing else 0.0,
        {
            "missing": missing,
            "present_factor_groups": present_groups,
            "missing_factor_groups": missing_groups,
            "structured_evidence_field": evidence_field,
            "structured_evidence_present": bool(structured_evidence),
        },
    )


def _numeric_series(artifact: dict[str, Any], field: str) -> list[float]:
    values = _get_any_field(artifact, [field], [])
    if not isinstance(values, list):
        return []
    result: list[float] = []
    for value in values:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            result.append(float(value))
        else:
            return []
    return result


def _bin_centers_from_artifact(artifact: dict[str, Any]) -> list[float]:
    centers = _get_any_field(artifact, FIELD_ALIASES["bin_centers"], [])
    if isinstance(centers, list) and centers:
        return [float(value) for value in centers if isinstance(value, (int, float)) and not isinstance(value, bool)]
    edges = _get_any_field(artifact, FIELD_ALIASES["bin_edges"], [])
    if not isinstance(edges, list) or len(edges) < 2:
        return []
    return [
        0.5 * (float(lo) + float(hi))
        for lo, hi in zip(edges[:-1], edges[1:])
        if isinstance(lo, (int, float)) and isinstance(hi, (int, float))
    ]


def _series_for_artifact(artifact: dict[str, Any], field: str) -> list[float]:
    if field == "data_minus_background":
        data = _numeric_series(artifact, "data_counts")
        background = _numeric_series(artifact, "total_background_counts") or _numeric_series(artifact, "background_counts")
        if len(data) == len(background):
            return [left - right for left, right in zip(data, background)]
        return []
    return _numeric_series(artifact, field)


def _interval_overlap_width(left: list[Any], right: list[Any]) -> float:
    if len(left) != 2 or len(right) != 2:
        return 0.0
    lo = max(float(left[0]), float(right[0]))
    hi = min(float(left[1]), float(right[1]))
    return max(0.0, hi - lo)


def _score_artifact_numeric_relationships(spec: dict[str, Any], artifacts: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    filename = spec.get("file")
    artifact = artifacts.get(filename, {}) if isinstance(filename, str) else {}
    if not isinstance(artifact, dict):
        return (0.0, {"reason": "missing_artifact", "file": filename})

    failures: list[dict[str, Any]] = []
    for relation in spec.get("required_relations", []) or []:
        if not isinstance(relation, dict):
            continue
        kind = relation.get("relation")
        if kind == "interval_overlaps":
            field = relation.get("field")
            value = artifact.get(field)
            target = relation.get("target_interval", [])
            overlap = _interval_overlap_width(value, target) if isinstance(value, list) and isinstance(target, list) else 0.0
            minimum = float(relation.get("minimum_overlap_width_gev", 0.0))
            if overlap < minimum:
                failures.append({"relation": kind, "field": field, "value": value, "target": target, "overlap": overlap})
        elif kind == "greater_or_equal":
            left = artifact.get(relation.get("left_field"))
            right = artifact.get(relation.get("right_field"))
            ok = isinstance(left, (int, float)) and isinstance(right, (int, float)) and float(left) >= float(right)
            if not ok:
                failures.append({"relation": kind, "left": left, "right": right})
        elif kind == "range":
            field = relation.get("field")
            value = artifact.get(field)
            expected = relation.get("expected_range", [])
            lo = expected[0] if isinstance(expected, list) and expected else None
            hi = expected[1] if isinstance(expected, list) and len(expected) > 1 else None
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
            ok = ok and (lo is None or float(value) >= float(lo)) and (hi is None or float(value) <= float(hi))
            if not ok:
                failures.append({"relation": kind, "field": field, "value": value, "expected_range": expected})
    return (1.0 if not failures else 0.0, {"failures": failures})


def _score_artifact_series_usable(spec: dict[str, Any], artifacts: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    filename = spec.get("file")
    field = spec.get("field")
    artifact = artifacts.get(filename, {}) if isinstance(filename, str) else {}
    if not isinstance(artifact, dict) or not isinstance(field, str):
        return (0.0, {"reason": "missing_artifact_or_field", "file": filename, "field": field})
    series = _numeric_series(artifact, field)
    requirements = set(spec.get("requirements", []) or [])
    failures: list[str] = []
    if "nonempty" in requirements and not series:
        failures.append("nonempty")
    if "nonnegative_values" in requirements and any(value < 0 for value in series):
        failures.append("nonnegative_values")
    if "finite_values" in requirements and any(not math.isfinite(value) for value in series):
        failures.append("finite_values")
    if "positive_sum" in requirements and sum(series) <= 0:
        failures.append("positive_sum")
    if "any_positive" in requirements and not any(value > 0 for value in series):
        failures.append("any_positive")
    if "aligned_with_bin_edges" in requirements:
        edges = _get_any_field(artifact, FIELD_ALIASES["bin_edges"], [])
        if not isinstance(edges, list) or len(edges) != len(series) + 1:
            failures.append("aligned_with_bin_edges")
    min_sum = spec.get("min_sum")
    if min_sum is not None and sum(series) < float(min_sum):
        failures.append(f"min_sum:{min_sum}")
    return (
        1.0 if not failures else 0.0,
        {
            "failures": failures,
            "count": len(series),
            "sum": sum(series),
            "max": max(series) if series else None,
        },
    )


def _label_matches_text(label: str, text: str, compact_text: str) -> bool:
    label_text = str(label).replace("_", " ").lower()
    return label_text in text or str(label).lower() in text or _compact_expr(str(label)) in compact_text


def _score_artifact_series_scale_plausibility(
    spec: dict[str, Any],
    artifacts: dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    filename = spec.get("file")
    artifact = artifacts.get(filename, {}) if isinstance(filename, str) else {}
    if not isinstance(artifact, dict):
        return (0.0, {"reason": "missing_artifact", "file": filename})

    centers = _bin_centers_from_artifact(artifact)
    observed = _series_for_artifact(artifact, str(spec.get("observed_field", "data_counts")))
    expected = _series_for_artifact(artifact, str(spec.get("expected_field", "total_background_counts")))
    if len(centers) != len(observed) or len(observed) != len(expected):
        return (
            0.0,
            {
                "reason": "missing_or_misaligned_histogram_data",
                "centers": len(centers),
                "observed": len(observed),
                "expected": len(expected),
            },
        )

    min_observed_sum = float(spec.get("min_observed_sum", 1.0))
    min_expected_sum = float(spec.get("min_expected_sum", 0.0))
    ratio_range = spec.get("expected_over_observed_sum_range", [0.0, float("inf")])
    ratio_lo = float(ratio_range[0]) if isinstance(ratio_range, list) and ratio_range else 0.0
    ratio_hi = float(ratio_range[1]) if isinstance(ratio_range, list) and len(ratio_range) > 1 else float("inf")
    max_bin_ratio = float(spec.get("max_expected_over_observed_bin_ratio", float("inf")))
    epsilon = float(spec.get("ratio_epsilon", 1e-9))

    raw_regions = spec.get("regions") or [{"name": "full", "interval": None}]
    regions: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_regions):
        if isinstance(raw, dict):
            regions.append(raw)
        elif isinstance(raw, list) and len(raw) == 2:
            regions.append({"name": f"region_{index}", "interval": raw})

    failures: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    for index, region in enumerate(regions):
        interval = region.get("interval")
        name = str(region.get("name", f"region_{index}"))
        selected = list(range(len(centers)))
        if isinstance(interval, list) and len(interval) == 2:
            lo, hi = float(interval[0]), float(interval[1])
            selected = [idx for idx, center in enumerate(centers) if lo <= center <= hi]
        if not selected:
            failures.append({"region": name, "reason": "no_bins_in_region", "interval": interval})
            checks.append({"region": name, "interval": interval, "bin_count": 0})
            continue

        observed_sum = sum(observed[idx] for idx in selected)
        expected_sum = sum(expected[idx] for idx in selected)
        ratio = expected_sum / max(observed_sum, epsilon)
        bin_ratios = [
            expected[idx] / max(observed[idx], epsilon)
            for idx in selected
            if observed[idx] > 0 or expected[idx] > 0
        ]
        max_ratio = max(bin_ratios) if bin_ratios else 0.0
        check = {
            "region": name,
            "interval": interval,
            "bin_count": len(selected),
            "observed_sum": observed_sum,
            "expected_sum": expected_sum,
            "expected_over_observed_sum_ratio": ratio,
            "max_expected_over_observed_bin_ratio": max_ratio,
        }
        checks.append(check)

        if observed_sum < min_observed_sum:
            failures.append({"region": name, "reason": "observed_sum_too_small", **check})
            continue
        if expected_sum < min_expected_sum:
            failures.append({"region": name, "reason": "expected_sum_too_small", **check})
        if not (ratio_lo <= ratio <= ratio_hi):
            failures.append({"region": name, "reason": "sum_ratio_out_of_range", "expected_range": [ratio_lo, ratio_hi], **check})
        if max_ratio > max_bin_ratio:
            failures.append({"region": name, "reason": "bin_ratio_too_large", "max_allowed": max_bin_ratio, **check})

    return (1.0 if not failures else 0.0, {"failures": failures, "checks": checks})


def _score_trace_execution_evidence_consistency(
    spec: dict[str, Any],
    submission_dir: Path,
    trace: dict[str, Any],
    artifacts: dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    evidence_field = str(spec.get("evidence_field", "execution_evidence"))
    evidence_obj = _get_path(trace, evidence_field, {})
    if not isinstance(evidence_obj, dict):
        return (0.0, {"reason": "missing_execution_evidence", "field": evidence_field})

    required_fields = spec.get(
        "required_fields",
        [
            "files_processed_count",
            "events_processed_total",
            "selected_events_total",
            "candidates_built_total",
            "histogram_filled_entries",
        ],
    )
    required_fields = [str(field) for field in required_fields]
    positive_fields = [str(field) for field in spec.get("required_positive_fields", required_fields)]
    require_integer = bool(spec.get("require_integer_counters", True))

    values: dict[str, float] = {}
    failures: list[dict[str, Any]] = []
    for field in required_fields:
        value = _get_path(evidence_obj, field)
        numeric = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))
        integer_ok = not require_integer or (isinstance(value, int) and not isinstance(value, bool))
        if not numeric or not integer_ok:
            failures.append({"field": field, "reason": "missing_or_invalid_counter", "value": value})
            continue
        values[field] = float(value)

    for field in positive_fields:
        if field in values and values[field] <= 0:
            failures.append({"field": field, "reason": "expected_positive", "value": values[field]})

    events_total = values.get("events_processed_total")
    selected_total = values.get("selected_events_total")
    if events_total is not None and selected_total is not None and selected_total > events_total:
        failures.append(
            {
                "field": "selected_events_total",
                "reason": "selected_exceeds_processed",
                "selected_events_total": selected_total,
                "events_processed_total": events_total,
            }
        )

    manifest_file = str(spec.get("input_manifest_file", "input_manifest.json"))
    manifest = _load_json_if_exists(submission_dir / manifest_file)
    manifest_file_count = None
    if isinstance(manifest, dict) and isinstance(manifest.get("files"), list):
        manifest_file_count = len(manifest.get("files") or [])
        files_processed = values.get("files_processed_count")
        if spec.get("require_files_processed_at_least_manifest_count") and files_processed is not None:
            if files_processed < manifest_file_count:
                failures.append(
                    {
                        "field": "files_processed_count",
                        "reason": "less_than_manifest_file_count",
                        "value": files_processed,
                        "manifest_file_count": manifest_file_count,
                    }
                )
        if spec.get("require_files_processed_equals_manifest_count") and files_processed is not None:
            if files_processed != manifest_file_count:
                failures.append(
                    {
                        "field": "files_processed_count",
                        "reason": "differs_from_manifest_file_count",
                        "value": files_processed,
                        "manifest_file_count": manifest_file_count,
                    }
                )

    spectrum_file = spec.get("spectrum_file")
    spectrum = artifacts.get(spectrum_file, {}) if isinstance(spectrum_file, str) else {}
    histogram_count_field = str(spec.get("histogram_count_field", "histogram_filled_entries"))
    histogram_count = values.get(histogram_count_field)
    series_evidence: dict[str, dict[str, Any]] = {}
    if isinstance(spectrum, dict):
        for field in spec.get("histogram_positive_series_fields", []) or []:
            field = str(field)
            series = _series_for_artifact(spectrum, field)
            series_sum = sum(series)
            series_evidence[field] = {"count": len(series), "sum": series_sum, "max": max(series) if series else None}
            if not series or series_sum <= 0:
                failures.append({"field": field, "reason": "spectrum_series_not_positive", "sum": series_sum})

        cover_field = spec.get("histogram_count_must_cover_series_field")
        if isinstance(cover_field, str) and histogram_count is not None:
            series = _series_for_artifact(spectrum, cover_field)
            series_sum = sum(series)
            tolerance = float(spec.get("histogram_count_cover_absolute_tolerance", 1e-6))
            if series and histogram_count + tolerance < series_sum:
                failures.append(
                    {
                        "field": histogram_count_field,
                        "reason": "histogram_count_below_series_sum",
                        "histogram_count": histogram_count,
                        "series_field": cover_field,
                        "series_sum": series_sum,
                    }
                )
    elif spectrum_file:
        failures.append({"field": "spectrum_file", "reason": "missing_spectrum_artifact", "file": spectrum_file})

    return (
        1.0 if not failures else 0.0,
        {
            "failures": failures,
            "counters": values,
            "manifest_file_count": manifest_file_count,
            "series": series_evidence,
        },
    )


def _score_histogram_excess_in_region(spec: dict[str, Any], artifacts: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    filename = spec.get("file")
    artifact = artifacts.get(filename, {}) if isinstance(filename, str) else {}
    if not isinstance(artifact, dict):
        return (0.0, {"reason": "missing_artifact", "file": filename})
    centers = _bin_centers_from_artifact(artifact)
    numerator = _series_for_artifact(artifact, str(spec.get("numerator_field", "data_counts")))
    denominator = _series_for_artifact(artifact, str(spec.get("denominator_field", "background_counts")))
    roi = spec.get("roi", [])
    if len(centers) != len(numerator) or len(numerator) != len(denominator) or not isinstance(roi, list) or len(roi) != 2:
        return (0.0, {"reason": "missing_or_misaligned_histogram_data"})
    diffs = [num - den for center, num, den in zip(centers, numerator, denominator) if float(roi[0]) <= center <= float(roi[1])]
    if not diffs:
        return (0.0, {"reason": "no_bins_in_roi"})
    integrated = sum(diffs)
    any_bin = max(diffs)
    ok = integrated > float(spec.get("require_integrated_difference_greater_than", float("-inf")))
    ok = ok and any_bin > float(spec.get("require_any_bin_difference_greater_than", float("-inf")))
    return (1.0 if ok else 0.0, {"integrated_difference": integrated, "max_bin_difference": any_bin})


def _score_histogram_peak_location(spec: dict[str, Any], artifacts: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    filename = spec.get("file")
    artifact = artifacts.get(filename, {}) if isinstance(filename, str) else {}
    if not isinstance(artifact, dict):
        return (0.0, {"reason": "missing_artifact", "file": filename})
    centers = _bin_centers_from_artifact(artifact)
    series_name = str(spec.get("primary_series", ""))
    series = _series_for_artifact(artifact, series_name)
    used_series = series_name
    if not series and spec.get("fallback_series"):
        used_series = str(spec.get("fallback_series"))
        series = _series_for_artifact(artifact, used_series)
    expected = spec.get("expected_range", [])
    if len(centers) != len(series) or not isinstance(expected, list) or len(expected) != 2:
        return (0.0, {"reason": "missing_or_misaligned_histogram_data", "series": used_series})
    peak_idx = max(range(len(series)), key=lambda idx: series[idx])
    peak_x = centers[peak_idx]
    peak_y = series[peak_idx]
    ok = float(expected[0]) <= peak_x <= float(expected[1])
    return (1.0 if ok else 0.0, {"peak_x": peak_x, "peak_y": peak_y, "series": used_series, "expected_range": expected})


def _score_validation_evidence(spec: dict[str, Any], submission_dir: Path, trace: dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    optional_files = spec.get("optional_files_any", [])
    existing = [filename for filename in optional_files if (submission_dir / filename).exists()]
    trace_text = _coerce_text(trace).lower()
    labels = spec.get("trace_stage_families_any_labels", spec.get("allowed_validation_types", []))
    compact = _compact_expr(trace_text)
    matching_labels = [label for label in labels if _label_matches_text(str(label), trace_text, compact)]

    alias_groups = spec.get("validation_type_aliases", {})
    matched_groups: dict[str, list[str]] = {}
    if isinstance(alias_groups, dict):
        for group, aliases in alias_groups.items():
            group_labels = [str(group)]
            if isinstance(aliases, list):
                group_labels.extend(str(alias) for alias in aliases)
            elif isinstance(aliases, str):
                group_labels.append(aliases)
            matched = [label for label in group_labels if _label_matches_text(label, trace_text, compact)]
            if matched:
                matched_groups[str(group)] = matched

    min_count = int(spec.get("minimum_count", 1))
    min_group_count = int(spec.get("minimum_group_count", 0))
    count = len(existing) + len(matching_labels)
    validation_fields = [
        field
        for field in ("validation_checks", "validation_actions", "cross_checks", "robustness_checks")
        if trace.get(field)
    ]
    generic_tokens = (
        "validation",
        "validate",
        "robust",
        "stability",
        "sideband",
        "alternative",
        "cross check",
        "cross-check",
        "sanity",
        "uncertainty",
        "scan",
        "variation",
    )
    generic_evidence = any(token in trace_text for token in generic_tokens)
    count += len(validation_fields)
    count += len(matched_groups)
    if spec.get("requires_result_record") and (generic_evidence or validation_fields):
        count += 1
    passed = count >= min_count
    if min_group_count:
        passed = passed and len(matched_groups) >= min_group_count
    return (
        1.0 if passed else 0.0,
        {
            "existing_files": existing,
            "matching_labels": matching_labels,
            "matched_groups": matched_groups,
            "minimum_group_count": min_group_count,
            "validation_fields": validation_fields,
            "generic_evidence": generic_evidence,
            "count": count,
        },
    )


def _has_validation_evidence(trace: dict[str, Any]) -> bool:
    score, evidence = _score_validation_evidence({"minimum_count": 1, "requires_result_record": True}, Path("."), trace)
    return bool(score) or bool(evidence.get("generic_evidence"))


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


def _numeric_value(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _relative_close(left: float, right: float, *, rel_tol: float, abs_tol: float) -> bool:
    return abs(left - right) <= max(abs_tol, rel_tol * max(1.0, abs(right)))


def _window_from_summary(summary: dict[str, Any], spec: dict[str, Any]) -> list[float]:
    configured = spec.get("signal_region") or spec.get("window") or spec.get("roi")
    if isinstance(configured, list) and len(configured) == 2:
        return [float(configured[0]), float(configured[1])]
    field = str(spec.get("summary_window_field", "signal_region"))
    value = summary.get(field)
    if isinstance(value, list) and len(value) == 2:
        return [float(value[0]), float(value[1])]
    return []


def _integrate_series_in_window(artifact: dict[str, Any], field: str, window: list[float]) -> float | None:
    series = _series_for_artifact(artifact, field)
    if not series or len(window) != 2:
        return None
    edges = _get_any_field(artifact, FIELD_ALIASES["bin_edges"], [])
    if isinstance(edges, list) and len(edges) == len(series) + 1:
        total = 0.0
        for lo, hi, value in zip(edges[:-1], edges[1:], series):
            if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
                return None
            width = float(hi) - float(lo)
            if width <= 0:
                return None
            overlap = _interval_overlap_width([lo, hi], window)
            if overlap > 0:
                total += float(value) * overlap / width
        return total
    centers = _bin_centers_from_artifact(artifact)
    if len(centers) == len(series):
        return sum(float(value) for center, value in zip(centers, series) if window[0] <= center <= window[1])
    return None


def _integrate_squared_series_in_window(artifact: dict[str, Any], field: str, window: list[float]) -> float | None:
    series = _series_for_artifact(artifact, field)
    if not series or len(window) != 2:
        return None
    edges = _get_any_field(artifact, FIELD_ALIASES["bin_edges"], [])
    if isinstance(edges, list) and len(edges) == len(series) + 1:
        total = 0.0
        for lo, hi, value in zip(edges[:-1], edges[1:], series):
            if not isinstance(lo, (int, float)) or not isinstance(hi, (int, float)):
                return None
            width = float(hi) - float(lo)
            if width <= 0:
                return None
            overlap = _interval_overlap_width([lo, hi], window)
            if overlap > 0:
                scaled = float(value) * overlap / width
                total += scaled * scaled
        return total
    centers = _bin_centers_from_artifact(artifact)
    if len(centers) == len(series):
        return sum(float(value) * float(value) for center, value in zip(centers, series) if window[0] <= center <= window[1])
    return None


def _score_artifact_window_consistency(
    spec: dict[str, Any],
    artifacts: dict[str, Any],
    trace: dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    spectrum_file = spec.get("spectrum_file")
    summary_file = spec.get("summary_file")
    spectrum = artifacts.get(spectrum_file, {}) if isinstance(spectrum_file, str) else {}
    summary = artifacts.get(summary_file, {}) if isinstance(summary_file, str) else {}
    if not isinstance(spectrum, dict) or not isinstance(summary, dict):
        return (0.0, {"reason": "missing_artifact", "spectrum_file": spectrum_file, "summary_file": summary_file})

    window = _window_from_summary(summary, spec)
    if len(window) != 2:
        return (0.0, {"reason": "missing_window"})

    data_field = str(spec.get("data_field", "data_counts"))
    background_field = str(spec.get("background_field", "total_background_counts"))
    background_uncertainty_field = str(spec.get("background_uncertainty_field", "total_background_uncertainty"))
    signal_field = spec.get("signal_field")
    data_yield = _integrate_series_in_window(spectrum, data_field, window)
    background_yield = _integrate_series_in_window(spectrum, background_field, window)
    background_variance = _integrate_squared_series_in_window(spectrum, background_uncertainty_field, window)
    signal_yield = _integrate_series_in_window(spectrum, str(signal_field), window) if isinstance(signal_field, str) else None
    if data_yield is None or background_yield is None:
        return (0.0, {"reason": "missing_window_series", "window": window})

    rel_tol = float(spec.get("relative_tolerance", 0.05))
    abs_tol = float(spec.get("absolute_tolerance", 1e-6))
    failures: list[dict[str, Any]] = []
    checks: dict[str, Any] = {
        "window": window,
        "derived_data_yield": data_yield,
        "derived_background_yield": background_yield,
        "derived_background_variance": background_variance,
        "derived_signal_yield": signal_yield,
    }

    summary_background_field = str(spec.get("summary_background_field", "window_background_yield"))
    summary_background = _numeric_value(summary.get(summary_background_field))
    if summary_background is not None:
        checks["summary_background_yield"] = summary_background
        if not _relative_close(summary_background, background_yield, rel_tol=rel_tol, abs_tol=abs_tol):
            failures.append({"field": summary_background_field, "summary": summary_background, "derived": background_yield})

    summary_data_field = spec.get("summary_data_field")
    if isinstance(summary_data_field, str):
        summary_data = _numeric_value(summary.get(summary_data_field))
        checks["summary_data_yield"] = summary_data
        if summary_data is None or not _relative_close(summary_data, data_yield, rel_tol=rel_tol, abs_tol=abs_tol):
            failures.append({"field": summary_data_field, "summary": summary_data, "derived": data_yield})

    summary_signal_field = spec.get("summary_signal_field")
    if isinstance(summary_signal_field, str):
        summary_signal = _numeric_value(summary.get(summary_signal_field))
        checks["summary_signal_yield"] = summary_signal
        if (
            summary_signal is None
            or signal_yield is None
            or not _relative_close(summary_signal, signal_yield, rel_tol=rel_tol, abs_tol=abs_tol)
        ):
            failures.append({"field": summary_signal_field, "summary": summary_signal, "derived": signal_yield})

    configured_formula = str(spec.get("significance_formula", "data_minus_background_over_sqrt_background"))
    summary_formula_field = str(spec.get("summary_significance_formula_field", "significance_formula"))
    declared_formula = _normalize_formula_key(summary.get(summary_formula_field))
    significance_formula = (
        declared_formula
        if configured_formula in {"declared_supported_formula", "declared_or_supported_formula"}
        else _normalize_formula_key(configured_formula)
    )
    allowed_formulas = [_normalize_formula_key(value) for value in spec.get("allowed_significance_formulas", []) or []]

    numerator_field = spec.get("summary_numerator_field")
    numerator_policy = str(spec.get("summary_numerator_policy", "data"))
    summary_numerator: float | None = None
    expected_numerator: float | None = None
    if isinstance(numerator_field, str):
        summary_numerator = _numeric_value(summary.get(numerator_field))
        if numerator_policy == "background_plus_signal":
            expected_numerator = None if signal_yield is None else background_yield + signal_yield
        elif numerator_policy == "data_minus_background":
            expected_numerator = data_yield - background_yield
        elif numerator_policy in {"declared_formula_numerator", "formula_numerator"}:
            if significance_formula in {
                "data_minus_background_over_sqrt_background",
                "data_minus_background_over_sqrt_background_plus_variance",
            }:
                expected_numerator = data_yield - background_yield
            elif significance_formula == "signal_over_sqrt_background":
                expected_numerator = signal_yield
            elif significance_formula == "background_plus_signal_over_sqrt_background_plus_fractional_systematic":
                expected_numerator = None if signal_yield is None else background_yield + signal_yield
            elif significance_formula == "numerator_minus_background_over_sqrt_background":
                expected_numerator = data_yield
            else:
                expected_numerator = data_yield
        else:
            expected_numerator = data_yield
        checks["summary_numerator_yield"] = summary_numerator
        checks["expected_numerator_yield"] = expected_numerator
        if (
            summary_numerator is None
            or expected_numerator is None
            or not _relative_close(summary_numerator, expected_numerator, rel_tol=rel_tol, abs_tol=abs_tol)
        ):
            failures.append({"field": numerator_field, "summary": summary_numerator, "derived": expected_numerator})

    significance_field = spec.get("significance_field", "significance_proxy")
    significance = _numeric_value(summary.get(str(significance_field)))
    expected_significance: float | None = None
    if allowed_formulas and significance_formula not in allowed_formulas:
        failures.append(
            {
                "field": summary_formula_field,
                "summary": summary.get(summary_formula_field),
                "reason": "unsupported_significance_formula",
                "allowed": allowed_formulas,
            }
        )
    if significance_formula == "data_minus_background_over_sqrt_background" and background_yield > 0:
        expected_significance = (data_yield - background_yield) / (background_yield ** 0.5)
    elif (
        significance_formula == "data_minus_background_over_sqrt_background_plus_variance"
        and background_yield > 0
        and background_variance is not None
    ):
        variance = background_yield + background_variance
        if variance > 0:
            expected_significance = (data_yield - background_yield) / (variance ** 0.5)
    elif significance_formula == "numerator_minus_background_over_sqrt_background" and background_yield > 0:
        numerator_for_significance = summary_numerator if summary_numerator is not None else expected_numerator
        if numerator_for_significance is not None:
            expected_significance = (numerator_for_significance - background_yield) / (background_yield ** 0.5)
    elif significance_formula == "signal_over_sqrt_background" and signal_yield is not None and background_yield > 0:
        expected_significance = signal_yield / (background_yield ** 0.5)
    elif significance_formula in {
        "numerator_over_sqrt_background_plus_fractional_systematic",
        "background_plus_signal_over_sqrt_background_plus_fractional_systematic",
    } and background_yield > 0:
        numerator_for_significance = summary_numerator if summary_numerator is not None else expected_numerator
        background_systematic_fraction = summary.get("background_systematic_fraction", spec.get("background_systematic_fraction", 0.0))
        background_systematic_fraction = float(background_systematic_fraction)
        variance = background_yield + background_systematic_fraction * background_yield * background_yield
        if numerator_for_significance is not None and variance > 0:
            expected_significance = numerator_for_significance / (variance ** 0.5)
    checks["summary_significance_formula"] = summary.get(summary_formula_field)
    checks["normalized_significance_formula"] = significance_formula
    checks["summary_significance"] = significance
    checks["expected_significance"] = expected_significance
    if significance is not None and expected_significance is not None:
        sig_abs_tol = float(spec.get("significance_absolute_tolerance", 0.05))
        sig_rel_tol = float(spec.get("significance_relative_tolerance", 0.05))
        if not _relative_close(significance, expected_significance, rel_tol=sig_rel_tol, abs_tol=sig_abs_tol):
            failures.append({"field": significance_field, "summary": significance, "derived": expected_significance})
    expected_significance_range = spec.get("expected_significance_range")
    if isinstance(expected_significance_range, list) and len(expected_significance_range) == 2:
        lo, hi = float(expected_significance_range[0]), float(expected_significance_range[1])
        if significance is None or not (lo <= significance <= hi):
            failures.append(
                {
                    "field": significance_field,
                    "summary": significance,
                    "reason": "outside_expected_significance_range",
                    "expected_range": [lo, hi],
                }
            )

    positive_yields = {
        "data": data_yield,
        "background": background_yield,
        "signal": signal_yield,
        "numerator": summary_numerator if summary_numerator is not None else expected_numerator,
        "significance": significance,
    }
    for label in spec.get("required_positive_window_yields", []) or []:
        value = positive_yields.get(str(label))
        if value is None or value <= 0:
            failures.append({"field": str(label), "reason": "expected_positive_window_value", "value": value})

    threshold = spec.get("validation_required_above_significance")
    validation_present = _has_validation_evidence(trace)
    checks["validation_evidence_present"] = validation_present
    if threshold is not None and significance is not None and abs(significance) >= float(threshold) and not validation_present:
        failures.append(
            {
                "field": significance_field,
                "summary": significance,
                "reason": "high_significance_without_validation_evidence",
                "threshold": float(threshold),
            }
        )

    return (1.0 if not failures else 0.0, {"failures": failures, **checks})


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
    if "file_nonempty" in condition:
        spec = condition["file_nonempty"]
        files = spec.get("files", []) if isinstance(spec, dict) else spec
        return _score_files_nonempty([str(name) for name in files], submission_dir)

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
                if not _selection_field_matches(actual, key, value):
                    actual_key = key.removesuffix("_any_of")
                    failures.append({"cut_id": expected["cut_id"], "field": key, "expected": value, "actual": actual.get(actual_key)})
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
    if "artifact_numeric_relationships" in condition:
        return _score_artifact_numeric_relationships(condition["artifact_numeric_relationships"], artifacts)
    if "artifact_window_consistency" in condition:
        return _score_artifact_window_consistency(condition["artifact_window_consistency"], artifacts, trace)
    if "artifact_series_usable" in condition:
        return _score_artifact_series_usable(condition["artifact_series_usable"], artifacts)
    if "artifact_series_scale_plausibility" in condition:
        return _score_artifact_series_scale_plausibility(condition["artifact_series_scale_plausibility"], artifacts)
    if "trace_execution_evidence_consistency" in condition:
        return _score_trace_execution_evidence_consistency(
            condition["trace_execution_evidence_consistency"],
            submission_dir,
            trace,
            artifacts,
        )
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
    if "file_nonempty" in condition:
        spec = condition["file_nonempty"]
        files = spec.get("files", []) if isinstance(spec, dict) else spec
        return _score_files_nonempty([str(name) for name in files], submission_dir)
    if "trace_required_fields" in condition:
        return _score_required_trace_fields(condition["trace_required_fields"], trace)
    if "trace_execution_evidence_consistency" in condition:
        return _score_trace_execution_evidence_consistency(
            condition["trace_execution_evidence_consistency"],
            submission_dir,
            trace,
            artifacts,
        )
    if "trace_stage_families_present" in condition:
        return _score_stage_families_present(condition["trace_stage_families_present"], trace)
    if "trace_stage_family_order" in condition:
        return _score_stage_family_order(condition["trace_stage_family_order"], trace)
    if "scientifically_valid_selection_evidence" in condition:
        return _score_selection_evidence(condition["scientifically_valid_selection_evidence"], trace)
    if "trace_data_assembly_semantics" in condition:
        return _score_trace_data_assembly_semantics(condition["trace_data_assembly_semantics"], submission_dir, trace)
    if "mc_weighting_strategy" in condition:
        return _score_mc_weighting_strategy(condition["mc_weighting_strategy"], trace)
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
    if "hzz_sample_manifest_coverage" in condition:
        return _score_hzz_sample_manifest_coverage(condition["hzz_sample_manifest_coverage"], submission_dir, trace)
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
    if "histogram_excess_in_region" in condition:
        return _score_histogram_excess_in_region(condition["histogram_excess_in_region"], artifacts)
    if "histogram_peak_location" in condition:
        return _score_histogram_peak_location(condition["histogram_peak_location"], artifacts)
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
