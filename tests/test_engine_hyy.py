from engine.evaluator import evaluate_task
from engine.package_loader import load_spec_bundle
from utils.mock_traces import mock_trace_hyy
from tasks.task_spec import TaskSpec

def test_engine_hyy_mock_passes_required_cuts():
    # We construct a mock task spec pointing to the specs/hyy directory
    # Note: specs/hyy might miss task_spec.yaml but we only need rubric.yaml for this test
    # providing we construct the TaskSpec object correctly.
    
    # We use a dummy TaskSpec object just to satisfy load_spec_bundle
    # or we can construct spec manually entirely.
    
    spec_dir = "specs/hyy"
    task_mock = {
        "spec_dir": spec_dir,
        "rubric_path": "rubric.yaml",
        "judge_prompt_path": "judge_prompt.md",
    }
    
    bundle = load_spec_bundle(task_mock) # {"rubric": ..., "eval_ref": ..., ...}
    
    spec = {
        "task": {"id": "t_hyy_test", "type": "hyy_analysis"},
        "rubric": bundle["rubric"],
        "eval_ref": bundle["eval_ref"],
        "judge_prompt": bundle["judge_prompt"],
    }

    trace = mock_trace_hyy("t_hyy_test")
    report = evaluate_task(spec=spec, trace=trace)

    rule_eval = report["rule"] # report structure changed? evaluate_task returns { "rule": {"score": ...}, ... }
    # evaluator.py: "rule": {"score": rule.rule_score}
    # It seems evaluate_task result structure is slightly different from what run_engine_for_task returned?
    # run_engine_for_task likely wrapped evaluate_task. 
    # Let's check evaluator.py again for exact return structure.
    
    assert report["hard_checks_passed"] is True
    assert report["rule"]["score"] > 0
    
    # checking signals
    signals = report.get("signals", {})
    assert signals.get("missing_cut_ids", []) == []
