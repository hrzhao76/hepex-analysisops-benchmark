
import json
import logging
from engine.evaluator import evaluate_task
from utils.mock_traces import get_mock_trace

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reproduce_check")

def run_check():
    # 1. Setup Inputs
    # using Hyy task input
    task_id = "hyy_repro_test"
    trace = get_mock_trace("hyy_analysis", task_id)
    
    # Minimal rubric that uses both gates and rule checks
    rubric = {
        "version": 1,
        "total": 100,
        "gates": [
             {"id": "trace_present", "type": "required_fields", "required_fields": ["status", "cuts"], "fail_total_score": 0}
        ],
        "rule_checks": [
            {"id": "check_cuts", "type": "check_cut_ids", "points": 50, "required_cut_ids": ["tight_id", "pt_abs"]},
            {"id": "check_mass", "type": "numeric_in_range", "points": 50, "value_path": "fit_result.center", "lo": 120.0, "hi": 130.0}
        ]
    }
    
    spec = {
        "task": {"id": task_id, "type": "hyy_analysis"},
        "rubric": rubric,
        "eval_ref": {},
        "judge_prompt": None
    }

    # 2. Run Evaluation Multiple Times
    logger.info("Running iteration 1...")
    result_1 = evaluate_task(spec, trace, gemini=None)
    
    logger.info("Running iteration 2...")
    result_2 = evaluate_task(spec, trace, gemini=None)
    
    # 3. Compare Results
    # We compare the JSON serialization to ensure everything is identical
    json_1 = json.dumps(result_1, sort_keys=True)
    json_2 = json.dumps(result_2, sort_keys=True)
    
    if json_1 == json_2:
        logger.info("SUCCESS: Results are identical.")
        print(f"Result Score: {result_1['final']['total_score']}")
    else:
        logger.error("FAILURE: Results differ!")
        print("Result 1:", json_1)
        print("Result 2:", json_2)
        exit(1)

if __name__ == "__main__":
    run_check()
