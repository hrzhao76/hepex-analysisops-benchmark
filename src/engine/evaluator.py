from __future__ import annotations
from typing import Any

def _index_by_cut_id(cutflow: list[dict]) -> dict[str, dict]:
    out = {}
    for row in cutflow:
        cid = row.get("cut_id")
        if cid:
            out[cid] = row
    return out

def evaluate_rule(workflow: dict, rubric: dict, trace: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    hard_failures: list[str] = []

    # ---- hard check: trace fields ----
    for hc in rubric.get("hard_checks", []):
        if hc["id"] == "trace_present":
            required_fields = hc.get("required_fields", [])
            missing = [f for f in required_fields if f not in trace]
            if missing:
                hard_failures.append(f"missing_fields:{missing}")

    if hard_failures:
        return {
            "hard_checks_passed": False,
            "hard_failures": hard_failures,
            "rule_score": 0.0,
            "rule_max": float(rubric.get("total", 100)),
            "issues": issues,
            "signals": {},
        }

    task_type = workflow.get("task_type")

    if task_type == "hyy_analysis":
        return _eval_hyy(workflow, rubric, trace)
    if task_type == "zpeak_fit":
        return _eval_zpeak_fit(workflow, rubric, trace)

    return {
        "hard_checks_passed": True,
        "hard_failures": [],
        "rule_score": 0.0,
        "rule_max": float(rubric.get("total", 100)),
        "issues": [{"severity":"error","code":"UNKNOWN_TASK_TYPE","message": f"Unknown task_type={task_type}"}],
        "signals": {},
    }


def _eval_hyy(workflow: dict, rubric: dict, trace: dict[str, Any]) -> dict[str, Any]:
    total = float(rubric.get("total", 100))
    issues = []
    signals = {}

    required_cut_ids = []
    for hc in rubric.get("hard_checks", []):
        if hc["id"] == "cutflow_has_all_required_cuts":
            required_cut_ids = hc.get("required_cut_ids", [])

    cutflow = trace.get("cutflow", [])
    cuts = trace.get("cuts", [])

    cut_ids_in_trace = [c.get("cut_id") for c in cuts if c.get("cut_id")]
    missing = [cid for cid in required_cut_ids if cid not in cut_ids_in_trace]
    if missing:
        issues.append({"severity":"error","code":"MISSING_CUTS","message": f"Missing cuts: {missing}"})
        signals["missing_cut_ids"] = missing

    # order check
    expected_order = [c["id"] for c in workflow["selection"]["cuts"]]
    if workflow["selection"].get("cut_order_enforced", False):
        # compare relative order of those present
        present_expected = [cid for cid in expected_order if cid in cut_ids_in_trace]
        present_trace = [cid for cid in cut_ids_in_trace if cid in expected_order]
        if present_trace != present_expected:
            issues.append({"severity":"warn","code":"ORDER_MISMATCH",
                           "message": f"Expected order {present_expected}, got {present_trace}"})
            signals["order_mismatch"] = {"expected": present_expected, "got": present_trace}

    # cutflow monotonic check
    cf_ok = True
    for row in cutflow:
        nb = row.get("n_before")
        na = row.get("n_after")
        if isinstance(nb, (int, float)) and isinstance(na, (int, float)) and na > nb:
            cf_ok = False
            issues.append({"severity":"warn","code":"CUTFLOW_NON_MONOTONIC",
                           "message": f"cut_id={row.get('cut_id')} n_after({na})>n_before({nb})"})
    signals["cutflow_monotonic"] = cf_ok

    # simple scoring (v0): start at total, subtract penalties
    score = total
    if missing:
        # rubric says severe; use fail_penalty if defined
        penalty = 0
        for hc in rubric.get("hard_checks", []):
            if hc["id"] == "cutflow_has_all_required_cuts":
                penalty = int(hc.get("fail_penalty", 40))
        score -= penalty
    if not cf_ok:
        score -= 10

    score = max(0.0, min(total, score))
    return {
        "hard_checks_passed": True,
        "hard_failures": [],
        "rule_score": score,
        "rule_max": total,
        "issues": issues,
        "signals": signals,
    }


def _eval_zpeak_fit(workflow: dict, rubric: dict, trace: dict[str, Any]) -> dict[str, Any]:
    total = float(rubric.get("total", 100))
    issues = []
    signals = {}

    fit = trace.get("fit_result", {})
    if not fit:
        issues.append({"severity":"error","code":"MISSING_FIT_RESULT","message":"fit_result missing"})
        return {
            "hard_checks_passed": True,
            "hard_failures": [],
            "rule_score": 0.0,
            "rule_max": total,
            "issues": issues,
            "signals": {"missing": ["fit_result"]},
        }

    mu = fit.get("mu")
    sigma = fit.get("sigma")
    gof = fit.get("gof", {})  # e.g. {"chi2_ndof":..., "p_value":...}

    # thresholds from workflow (structured)
    target_mu = workflow["fit_expectations"]["mu_target"]
    mu_tol = workflow["fit_expectations"]["mu_tolerance"]
    sigma_range = workflow["fit_expectations"]["sigma_range"]
    min_p = workflow["fit_expectations"].get("min_p_value", None)

    # score components (v0): mu closeness, sigma range, gof, method metadata completeness
    score = 0.0

    # (1) peak position
    if isinstance(mu, (int, float)):
        d = abs(mu - target_mu)
        if d <= mu_tol:
            score += 40
        else:
            score += max(0.0, 40 * (1 - d / (3 * mu_tol)))
            issues.append({"severity":"warn","code":"MU_OFF",
                           "message": f"mu={mu} far from target {target_mu} (tol {mu_tol})"})
        signals["mu"] = mu
    else:
        issues.append({"severity":"error","code":"MU_MISSING","message":"fit_result.mu missing"})

    # (2) width
    if isinstance(sigma, (int, float)):
        lo, hi = sigma_range
        if lo <= sigma <= hi:
            score += 20
        else:
            issues.append({"severity":"warn","code":"SIGMA_OUT_OF_RANGE",
                           "message": f"sigma={sigma} not in [{lo},{hi}]"})
            score += 5
        signals["sigma"] = sigma
    else:
        issues.append({"severity":"error","code":"SIGMA_MISSING","message":"fit_result.sigma missing"})

    # (3) goodness-of-fit
    pval = gof.get("p_value")
    if isinstance(pval, (int, float)) and min_p is not None:
        if pval >= min_p:
            score += 20
        else:
            score += 5
            issues.append({"severity":"warn","code":"LOW_PVALUE","message": f"p_value={pval} < {min_p}"})
        signals["p_value"] = pval
    else:
        # if p-value not provided, partial credit
        score += 10
        issues.append({"severity":"info","code":"GOF_PARTIAL","message":"No p_value provided; partial credit"})

    # (4) method trace completeness (fit_method block)
    method = trace.get("fit_method", {})
    required_keys = workflow["fit_expectations"]["method_required_fields"]
    missing = [k for k in required_keys if k not in method]
    if not missing:
        score += 20
    else:
        score += max(0.0, 20 - 5 * len(missing))
        issues.append({"severity":"warn","code":"METHOD_METADATA_MISSING",
                       "message": f"fit_method missing fields: {missing}"})
        signals["missing_fit_method_fields"] = missing

    score = max(0.0, min(total, score))
    return {
        "hard_checks_passed": True,
        "hard_failures": [],
        "rule_score": score,
        "rule_max": total,
        "issues": issues,
        "signals": signals,
    }
