from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field


class TaskSpec(BaseModel):
    # identity
    id: str
    type: str
    mode: Literal["mock", "call_white"] = "mock"

    # execution/data requirements
    needs_data: bool = True
    release: str = "2025e-13tev-beta"
    dataset: str = "data"
    skim: str
    protocol: str = "https"
    max_files: int = 3
    cache: bool = True
    reuse_existing: bool = True

    # evaluation specs (relative to spec_dir by default)
    # NOTE: spec_dir is only used for V1 specs/ layout; V2 tasks_public/ tasks omit it.
    spec_dir: Optional[str] = None

    # --- Transitional compatibility fields ---
    # These fields exist only for backward-compat with V1 specs/ layout.
    # They should be removed in a later cleanup phase once private eval is
    # fully decoupled from the public task contract.
    rubric_path: Optional[str] = None
    judge_prompt_path: Optional[str] = None
    eval_ref_path: Optional[str] = None
    white_prompt_path: Optional[str] = None  # V1 alias; prefer solver_prompt_path

    # V2 public contract: solver prompt path
    solver_prompt_path: Optional[str] = "solver_prompt.md"

    # (optional) task description & constraints
    description: Optional[str] = None
    constraints: dict[str, Any] = Field(default_factory=dict)

    def resolve_path(self, rel: str | None) -> Optional[Path]:
        if not rel:
            return None
        if self.spec_dir is None:
            return None
        p = Path(self.spec_dir) / rel
        return p


class GreenConfig(BaseModel):
    data_dir: str = "/tmp/atlas_data_cache"
    # V2: task directories live under tasks_public/ with numeric prefix.
    # V1 specs/ paths still accepted for backward compatibility.
    task_dirs: list[str] = Field(default_factory=lambda: ["tasks_public/t001_zpeak_fit"])


def load_task_spec(spec_dir: str | Path) -> TaskSpec:
    spec_dir = str(spec_dir)
    path = Path(spec_dir) / "task_spec.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    # Inject spec_dir so package_loader can resolve relative paths (V1 compat)
    data.setdefault("spec_dir", spec_dir)

    return TaskSpec.model_validate(data)
