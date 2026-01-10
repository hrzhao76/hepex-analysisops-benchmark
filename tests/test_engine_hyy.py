from engine.runner import run_engine_for_task
from utils.mock_traces import mock_trace_hyy
from tasks.task_spec import HyyAnalysisTaskSpec

def test_engine_hyy_mock_passes_required_cuts():
    task = HyyAnalysisTaskSpec(
        id="t_hyy_test",
        mode="mock",
        workflow_spec_path="specs/hyy/workflow.yaml",
        rubric_path="specs/hyy/rubric.yaml",
        judge_prompt_path="specs/hyy/judge_prompt.md",
    )

    trace = mock_trace_hyy(task.id)
    report = run_engine_for_task(task_spec=task, data_info=None, submission_trace=trace)

    rule_eval = report["final"]["rule_eval"]
    assert rule_eval["hard_checks_passed"] is True
    assert rule_eval["rule_score"] > 0

    # should not report missing cuts in the mock
    signals = rule_eval.get("signals", {})
    assert signals.get("missing_cut_ids", []) == []
