from pathlib import Path

import yaml

from tasks.task_spec import load_task_spec


ROOT = Path(__file__).parent.parent
TASKS_PUBLIC = ROOT / "tasks_public"


def public_task_dirs() -> list[Path]:
    return sorted(path for path in TASKS_PUBLIC.iterdir() if (path / "task_spec.yaml").exists())


def test_public_tasks_use_bundle_directory_contract():
    assert public_task_dirs(), "No public tasks found"

    for task_dir in public_task_dirs():
        task = load_task_spec(task_dir)
        assert task.solver_response_mode == "submission_bundle_v1"
        assert task.evaluation_mode == "directory_contract_and_private_rubric_v1"
        assert (task_dir / "solver_prompt.md").exists()
        assert (task_dir / "submission_contract.yaml").exists()


def test_public_contracts_use_required_outputs_schema():
    for task_dir in public_task_dirs():
        contract = yaml.safe_load((task_dir / "submission_contract.yaml").read_text(encoding="utf-8")) or {}
        assert isinstance(contract.get("required_outputs"), list), task_dir
        assert contract["required_outputs"], task_dir
        assert isinstance(contract.get("schemas"), dict), task_dir

        filenames = {entry["canonical_filename"] for entry in contract["required_outputs"]}
        assert filenames <= set(contract["schemas"]), task_dir
