
import pytest
from pathlib import Path
from engine.package_loader import load_spec_bundle
from engine.evaluator import evaluate_task
from utils.mock_traces import get_mock_trace

SPECS_DIR = Path(__file__).parent.parent / "specs"

def get_task_dirs():
    """Discover all task directories in specs/."""
    if not SPECS_DIR.exists():
        return []
    return [d for d in SPECS_DIR.iterdir() if d.is_dir() and (d / "task_spec.yaml").exists()]

@pytest.mark.parametrize("task_dir", get_task_dirs(), ids=lambda d: d.name)
def test_task_evaluation(task_dir):
    """
    Generic test that:
    1. Loads the task spec bundle from the directory.
    2. Retrieves the mock trace for the task.
    3. Runs the evaluation engine.
    4. Asserts that the evaluation completes and returns a result.
    """
    import yaml

    # 1. Load Task Config
    task_spec_path = task_dir / "task_spec.yaml"
    try:
        task_config = yaml.safe_load(task_spec_path.read_text())
        task_config["spec_dir"] = str(task_dir)
        
        # Load the bundle (rubric, eval_ref, etc.)
        bundle = load_spec_bundle(task_config)
        
        # Construct the full evaluation spec
        spec = {
            "task": task_config,
            "rubric": bundle["rubric"],
            "eval_ref": bundle["eval_ref"],
            "judge_prompt": bundle["judge_prompt"],
            # white_prompt is optional for evaluation but good to have in bundle
        }
    except Exception as e:
        pytest.fail(f"Failed to load spec bundle for {task_dir.name}: {e}")

    task_id = task_config["id"]
    task_type = task_config["type"]

    # 2. Get Mock Trace
    try:
        trace = get_mock_trace(task_type, task_id)
    except ValueError as e:
        # If no mock trace is defined/registered yet, we might skip or fail.
        # For now, let's fail to ensure we remember to add it.
        pytest.fail(f"No mock trace registered for task type '{task_type}': {e}")

    # 3. Evaluate
    # Pass gemini=None because we don't want to use real LLM for logic checks if possible,
    # or ensure mock trace covers everything.
    # Note: If judge_prompt needs simple checking, gemini=None might fail if the code relies on it.
    # But for rule-based grading (which is preferred in this benchmark), it should work or Mock Gemini.
    result = evaluate_task(spec, trace, gemini=None)

    # 4. Assertions
    assert "final" in result
    assert "total_score" in result["final"]
    # We expect the mock trace to be "perfect" or at least valid enough to get a score.
    # Let's assert score is not None.
    assert result["final"]["total_score"] is not None
    print(f"Task {task_dir.name} Score: {result['final']['total_score']}")
