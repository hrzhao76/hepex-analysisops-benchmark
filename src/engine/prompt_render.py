# src/engine/prompt_render.py
from __future__ import annotations
import json
from typing import Any, Dict, List

def pretty(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True)

def render_judge_prompt(template: str,
                        *,
                        rubric: Dict[str, Any],
                        eval_ref: Dict[str, Any],
                        trace: Dict[str, Any],
                        rule_signals: Dict[str, Any],
                        rule_issues: List[Dict[str, Any]]) -> str:
    return (template
            .replace("{{RUBRIC}}", pretty(rubric))
            .replace("{{EVAL_REF}}", pretty(eval_ref))
            .replace("{{WORKFLOW_REF}}", pretty(eval_ref))
            .replace("{{SUBMISSION_EVIDENCE}}", pretty(trace))
            .replace("{{RULE_SIGNALS}}", pretty(rule_signals))
            .replace("{{RULE_ISSUES}}", pretty(rule_issues)))

def _builtin_minimal_prompt(task_id: str, task_type: str) -> str:
    return f"""
You are solving a benchmark task.

Task ID: {task_id}
Task Type: {task_type}

You must return a submission_bundle_v1 JSON object.
The bundle artifacts will be materialized and validated against the public contract.

Required rules:
- Output JSON only. No extra text.
- If the task fails, set top-level "status" = "error" and explain briefly in an artifact when possible.

Minimum response shape:
{{
  "status": "ok" | "error",
  "artifacts": {{
    "<canonical_filename>": object | string
  }}
}}

Notes:
- Use exactly the canonical filenames declared in submission_contract.yaml.
- Missing artifacts or schema fields will fail the public contract.
"""
