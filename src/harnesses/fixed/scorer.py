from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import json
import math
import re


@dataclass
class ScoreResult:
    score: float
    correct: int
    total: int
    per_item: list[dict[str, Any]]
    parse_ok: bool
    parsed_z_scores: list[float] | None
    raw_response: str


_FLOAT_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _extract_numbers(text: str) -> list[float]:
    nums = _FLOAT_RE.findall(text)
    out: list[float] = []
    for x in nums:
        try:
            out.append(float(x))
        except Exception:
            continue
    return out


def parse_white_zscores(text: str, n: int, output_key: str = "z_scores") -> list[float] | None:
    """
    Parse white agent response. Prefer JSON: {"z_scores":[...]}.
    Fallback: extract first n floats from text.
    """
    # JSON preferred
    try:
        obj = json.loads(text)
        if isinstance(obj, dict) and isinstance(obj.get(output_key), list):
            zs = [float(v) for v in obj[output_key]]
            return zs
    except Exception:
        pass

    # Fallback: extract numbers
    nums = _extract_numbers(text)
    if len(nums) >= n:
        return nums[:n]
    return None


def score_fixed_accuracy(
    *,
    spec: dict[str, Any],
    white_text: str,
) -> ScoreResult:
    """
    Fixed-harness scoring: compare predicted z_scores against rubric.ground_truth
    using absolute error tolerance. Matching is by_position (v0).
    """

    rubric = spec.get("rubric", {}) or {}
    tolerance = float(rubric.get("tolerance", 1e-4))
    matching = rubric.get("matching", "by_position")
    if matching != "by_position":
        # v0: keep it strict; you can expand later
        raise ValueError(f"Unsupported matching mode: {matching}")

    ground_truth = rubric.get("ground_truth", []) or []
    if not isinstance(ground_truth, list) or len(ground_truth) == 0:
        raise ValueError("rubric.ground_truth must be a non-empty list")

    p_values: list[float] = []
    z_true: list[float] = []
    for row in ground_truth:
        if not isinstance(row, dict) or "p" not in row or "z" not in row:
            raise ValueError("Each ground_truth entry must be a dict with keys: p, z")
        p_values.append(float(row["p"]))
        z_true.append(float(row["z"]))

    output_key = (spec.get("white_agent", {}) or {}).get("output_key", "z_scores")
    z_pred = parse_white_zscores(white_text, n=len(p_values), output_key=output_key)

    per_item: list[dict[str, Any]] = []
    correct = 0
    for i, p in enumerate(p_values):
        true_i = z_true[i]
        pred_i = None if z_pred is None or i >= len(z_pred) else float(z_pred[i])

        if pred_i is None or math.isnan(pred_i):
            ok_i = False
            err = None
        else:
            err = abs(pred_i - true_i)
            ok_i = err <= tolerance

        if ok_i:
            correct += 1

        per_item.append(
            {
                "p": p,
                "z_true": true_i,
                "z_pred": pred_i,
                "abs_err": err,
                "ok": ok_i,
            }
        )

    total = len(p_values)
    score = correct / total if total else 0.0
    parse_ok = z_pred is not None and len(z_pred) >= total

    return ScoreResult(
        score=score,
        correct=correct,
        total=total,
        per_item=per_item,
        parse_ok=parse_ok,
        parsed_z_scores=z_pred,
        raw_response=white_text[:2000],
    )
