from engine.evaluator import evaluate_task
from engine.package_loader import load_spec_bundle
from utils.mock_traces import mock_trace_zpeak_fit

def test_engine_zpeak_fit_mock_scores_positive():
    spec_dir = "specs/zpeak_fit"
    task_mock = {
        "spec_dir": spec_dir,
        "rubric_path": "rubric.yaml",
        "judge_prompt_path": "judge_prompt.md",
    }
    
    bundle = load_spec_bundle(task_mock)
    
    spec = {
        "task": {"id": "t_zpeak_fit_test", "type": "zpeak_fit"},
        "rubric": bundle["rubric"],
        "eval_ref": bundle["eval_ref"],
        "judge_prompt": bundle["judge_prompt"],
    }
    
    trace = mock_trace_zpeak_fit("t_zpeak_fit_test")
    report = evaluate_task(spec=spec, trace=trace)

    assert report["final"]["total_score"] > 0
    assert report["final"]["max_score"] == 100
