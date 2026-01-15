# src/engine/checks.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

def get_path(obj: Any, path: str, default: Any = None) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur

def is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

@dataclass
class CheckResult:
    passed: bool               # gate 用：False 代表 gate fail；rule 一般 True
    points: float              # 本 check 得分
    max_points: float          # 本 check 满分
    issues: List[Dict[str, Any]]
    signals: Dict[str, Any]

CheckFn = Callable[[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]], CheckResult]
# (check_cfg, trace, rubric, workflow_ref) -> CheckResult


def required_fields(cfg, trace, rubric, wf) -> CheckResult:
    required = cfg.get("required_fields", [])
    missing = [f for f in required if f not in trace]
    if missing:
        return CheckResult(
            passed=False,
            points=0.0,
            max_points=0.0,
            issues=[{"severity":"error","code":"MISSING_FIELDS","message":f"Missing fields: {missing}"}],
            signals={"missing_fields": missing},
        )
    return CheckResult(True, 0.0, 0.0, [], {})


def numeric_in_range(cfg, trace, rubric, wf) -> CheckResult:
    pts = float(cfg.get("points", 0.0))
    v = get_path(trace, cfg["value_path"], None)

    # range: either (lo,hi) or from workflow_ref via range_path
    if "range_path" in cfg:
        r = get_path(wf, cfg["range_path"], None)
        lo, hi = (float(r[0]), float(r[1])) if isinstance(r, list) and len(r) == 2 else (None, None)
    else:
        lo, hi = float(cfg["lo"]), float(cfg["hi"])

    gate = bool(cfg.get("gate", False))
    if not is_number(v) or lo is None or hi is None:
        return CheckResult(
            passed=(False if gate else True),
            points=0.0,
            max_points=pts,
            issues=[{"severity":"error" if gate else "warn","code":"VALUE_MISSING","message":f"Missing value: {cfg['value_path']}"}],
            signals={},
        )

    v = float(v)
    ok = (lo <= v <= hi)
    if ok:
        return CheckResult(True, pts, pts, [], {cfg.get("signal_key", cfg["value_path"]): v})

    out_pts = float(cfg.get("out_of_range_points", 0.0))
    return CheckResult(
        passed=(False if gate else True),
        points=out_pts,
        max_points=pts,
        issues=[{"severity":"warn","code":"OUT_OF_RANGE","message":f"value={v} not in [{lo},{hi}]"}],
        signals={cfg.get("signal_key", cfg["value_path"]): v},
    )


def threshold_ge(cfg, trace, rubric, wf) -> CheckResult:
    pts = float(cfg.get("points", 0.0))
    v = get_path(trace, cfg["value_path"], None)

    thr = cfg.get("threshold")
    if thr is None and "threshold_path" in cfg:
        thr = get_path(wf, cfg["threshold_path"], None)
    thr = float(thr) if thr is not None else None

    missing_pts = float(cfg.get("missing_points", 0.0))

    if not is_number(v) or thr is None:
        return CheckResult(True, missing_pts, pts,
                           [{"severity":"info","code":"THRESHOLD_MISSING","message":"Missing value/threshold; partial credit"}],
                           {})

    v = float(v)
    if v >= thr:
        return CheckResult(True, pts, pts, [], {cfg.get("signal_key", cfg["value_path"]): v})

    return CheckResult(True, 0.0, pts,
                       [{"severity":"warn","code":"BELOW_THRESHOLD","message":f"value={v} < {thr}"}],
                       {cfg.get("signal_key", cfg["value_path"]): v})


def target_soft(cfg, trace, rubric, wf) -> CheckResult:
    pts = float(cfg.get("points", 0.0))
    soft_factor = float(cfg.get("soft_factor", 3.0))

    v = get_path(trace, cfg["value_path"], None)

    target = cfg.get("target")
    if target is None and "target_path" in cfg:
        target = get_path(wf, cfg["target_path"], None)

    tol = cfg.get("tolerance")
    if tol is None and "tolerance_path" in cfg:
        tol = get_path(wf, cfg["tolerance_path"], None)

    if not is_number(v) or target is None or tol is None:
        return CheckResult(True, 0.0, pts, [{"severity":"error","code":"TARGET_MISSING","message":"Missing value/target/tolerance"}], {})

    v = float(v)
    target = float(target)
    tol = max(1e-9, float(tol))
    d = abs(v - target)

    if d <= tol:
        got = pts
        issues = []
    else:
        got = max(0.0, pts * (1.0 - d / (soft_factor * tol)))
        issues = [{"severity":"warn","code":"TARGET_OFF","message":f"value={v} far from target {target} (tol {tol})"}]

    return CheckResult(True, got, pts, issues, {cfg.get("signal_key", cfg["value_path"]): v})


def required_keys_in_dict(cfg, trace, rubric, wf) -> CheckResult:
    pts = float(cfg.get("points", 0.0))
    penalty = float(cfg.get("missing_penalty_per_key", 5.0))

    d = get_path(trace, cfg["dict_path"], None)
    req = cfg.get("required_keys")
    if req is None and "required_keys_path" in cfg:
        req = get_path(wf, cfg["required_keys_path"], [])
    req = req or []

    missing: list[str] = []
    if not isinstance(d, dict):
        missing = list(req)
    else:
        for k in req:
            if k not in d:
                missing.append(k)
            else:
                if cfg.get("treat_empty_as_missing", True):
                    vv = d.get(k)
                    if vv is None or (isinstance(vv, str) and not vv.strip()):
                        missing.append(k)

    if not missing:
        return CheckResult(True, pts, pts, [], {})

    got = max(0.0, pts - penalty * len(missing))
    return CheckResult(True, got, pts,
                       [{"severity":"warn","code":"REQUIRED_KEYS_MISSING","message":f"Missing keys: {missing}"}],
                       {cfg.get("signal_key","missing_keys"): missing})



def check_cut_ids(cfg, trace, rubric, wf) -> CheckResult:
    pts = float(cfg.get("points", 0.0))
    req_ids = cfg.get("required_cut_ids", [])
    cuts = trace.get("cuts", [])
    
    if not isinstance(cuts, list):
         return CheckResult(False, 0.0, pts, [{"severity":"error","code":"INVALID_CUTS", "message":"trace['cuts'] must be a list"}], {})

    found_ids = {c.get("cut_id") for c in cuts if isinstance(c, dict)}
    missing = [rid for rid in req_ids if rid not in found_ids]
    
    gate = bool(cfg.get("gate", False))
    
    if missing:
        return CheckResult(
            passed=(False if gate else True),
            points=0.0,
            max_points=pts,
            issues=[{"severity":"error","code":"MISSING_CUT_IDS", "message":f"Missing cut IDs: {missing}"}],
            signals={"missing_cut_ids": missing}
        )
    
    return CheckResult(True, pts, pts, [], {"missing_cut_ids": []})


REGISTRY: Dict[str, CheckFn] = {
    "required_fields": required_fields,
    "numeric_in_range": numeric_in_range,
    "threshold_ge": threshold_ge,
    "target_soft": target_soft,
    "required_keys_in_dict": required_keys_in_dict,
    "check_cut_ids": check_cut_ids,
}
