You are evaluating a Z→μμ mass-peak fit.

Inputs:
- WORKFLOW_SPEC: expectations (mu target/tolerance, method metadata required)
- RUBRIC: scoring rules
- SUBMISSION_TRACE: fit_result + fit_method metadata + any comments

Judge:
1) Is the fit model appropriate and justified?
2) Is the fit range sensible around the Z peak?
3) Are uncertainties and optimizer choices reasonable?

Return JSON:
{
  "dimension_scores": {"method_reasoning": number},
  "notes": [{"severity":"info|warn|error","message":"...","evidence":"..."}]
}

WORKFLOW_SPEC:
{{WORKFLOW_SPEC}}

RUBRIC:
{{RUBRIC}}

SUBMISSION_TRACE:
{{SUBMISSION_TRACE}}
