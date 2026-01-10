from engine.runner import run_engine_for_task
from utils.mock_traces import mock_trace_zpeak_fit
from tasks.task_spec import ZPeakFitTaskSpec

def test_engine_zpeak_fit_mock_scores_positive():
    task = ZPeakFitTaskSpec(
        id="t_zpeak_fit_test",
        mode="mock",
        workflow_spec_path="specs/zpeak_fit/workflow.yaml",
        rubric_path="specs/zpeak_fit/rubric.yaml",
        judge_prompt_path="specs/zpeak_fit/judge_prompt.md",
    )

    trace = mock_trace_zpeak_fit(task.id)
    report = run_engine_for_task(task_spec=task, data_info=None, submission_trace=trace)

    assert report["task_id"] == task.id
    assert report["type"] == "zpeak_fit"
    assert "final" in report
    assert report["final"]["total_score"] > 0
    assert report["final"]["max_score"] == 100
