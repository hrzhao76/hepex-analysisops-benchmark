from __future__ import annotations
from typing import Any, Optional

from engine.package_loader import load_task_package
from engine.evaluator import evaluate_rule
from engine.aggregator import aggregate

def run_engine_for_task(
    *,
    task_spec: Any,
    data_info: Optional[dict[str, Any]],
    submission_trace: dict[str, Any],
) -> dict[str, Any]:
    pkg = load_task_package(task_spec.workflow_spec_path, task_spec.rubric_path, task_spec.judge_prompt_path)

    # rule-based evaluation
    rule_eval = evaluate_rule(pkg.workflow, pkg.rubric, submission_trace)

    # v0: no llm
    llm_eval = None

    final = aggregate(pkg.rubric, rule_eval, llm_eval)
    return {
        "task_id": getattr(task_spec, "id", "unknown"),
        "type": getattr(task_spec, "type", "unknown"),
        "status": "ok" if final["total_score"] > 0 else "error",
        "data_info": data_info,
        "submission_trace": submission_trace,
        "final": final,
    }
