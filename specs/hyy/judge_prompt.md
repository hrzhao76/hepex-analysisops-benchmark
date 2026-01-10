You are grading a physics analysis workflow for an H→γγ-style task.

You are given:
1) WORKFLOW_SPEC (YAML): the reference-guided expected workflow (cuts, order, intent, thresholds)
2) RUBRIC (YAML): scoring dimensions and hard checks
3) SUBMISSION_TRACE (JSON): the agent's reported workflow, including:
   - cuts: ordered list with cut_id, expression, and optional explanation
   - cutflow: table-like list with n_before/n_after per cut
   - artifacts: produced outputs
   - derived_variables (optional): how m_yy was computed

Instructions:
- Be conservative: if evidence is missing, do not award points.
- Accept logically equivalent expressions (e.g., DeMorgan transformations) if thresholds and intent match.
- Pay attention to dependency: pt_rel_myy must come after m_yy is computed.
- Crack veto intent: exclude |eta| in [1.37, 1.52]. Equivalent forms OK.

Return JSON only, with this schema:
{
  "hard_checks_passed": true/false,
  "hard_check_failures": ["..."],
  "dimension_scores": { "<dimension_id>": number },
  "total_score": number,
  "notes": [
    {"severity": "info|warn|error", "message": "...", "evidence": "..."}
  ]
}

WORKFLOW_SPEC:
{{WORKFLOW_SPEC}}

RUBRIC:
{{RUBRIC}}

SUBMISSION_TRACE:
{{SUBMISSION_TRACE}}
