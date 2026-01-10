from __future__ import annotations
from typing import Any, Optional

def aggregate(rubric: dict, rule_eval: dict[str, Any], llm_eval: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    # v0: rule score as final score
    total = float(rubric.get("total", 100))
    final = rule_eval["rule_score"]

    return {
        "total_score": max(0.0, min(total, float(final))),
        "max_score": total,
        "rule_eval": rule_eval,
        "llm_eval": llm_eval,
    }
