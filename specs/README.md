# Task Specifications

This directory contains the specifications for the benchmark tasks.

## How to Add New Tasks

This guide explains how to add a new physics analysis task to the benchmark. A "task" corresponds to a specific physics analysis workflow (e.g., Z peak fit, H->yy analysis).

### 1. Create Task Directory
Create a new directory in `specs/`:
```bash
mkdir specs/my_new_task
```

### 2. Create Required Files
Each task directory must contain the following 5 files:

1.  **`task_spec.yaml`**: The execution and environment contract.
2.  **`rubric.yaml`**: Scoring rules (gates, rule_checks, llm_checks).
3.  **`eval_ref.yaml`**: Evaluation reference data (expected values).
4.  **`white_prompt.md`**: Detailed task instructions for the White Agent (solver).
5.  **`judge_prompt.md`**: Prompt for the LLM Judge (if using LLM checks).

### Example Structure
```
specs/
  hyy/
    task_spec.yaml
    rubric.yaml
    eval_ref.yaml
    white_prompt.md
    judge_prompt.md
```

### File Details

#### `task_spec.yaml`
```yaml
id: "my_task"
type: "physics_analysis"
needs_data: true
rubric_path: "rubric.yaml"
eval_ref_path: "eval_ref.yaml"
white_prompt_path: "white_prompt.md"
judge_prompt_path: "judge_prompt.md"
```

#### `rubric.yaml`
```yaml
version: 1
total: 100
gates:
  - id: trace_present
    type: required_fields
    required_fields: [status, cuts]
rule_checks:
  - id: check_mass
    type: numeric_in_range
    value_path: "fit_result.mass"
    lo: 90.0
    hi: 92.0
```

### 3. Verification
1.  Add a mock trace to `src/utils/mock_traces.py`.
2.  Add a test case in `tests/` to verify the rubric scores the mock trace correctly.
