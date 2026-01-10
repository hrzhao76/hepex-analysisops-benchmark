from __future__ import annotations
from dataclasses import dataclass
from utils.loaders import load_yaml, load_text

@dataclass
class TaskPackage:
    workflow: dict
    rubric: dict
    judge_prompt: str

def load_task_package(workflow_path: str, rubric_path: str, prompt_path: str) -> TaskPackage:
    return TaskPackage(
        workflow=load_yaml(workflow_path),
        rubric=load_yaml(rubric_path),
        judge_prompt=load_text(prompt_path),
    )
