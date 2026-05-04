from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field, model_validator

from engine.schema_validator import require_valid, validate_task_package_dir, validate_task_spec_document


EvaluationMode = Literal["directory_contract_and_private_l1", "directory_contract_and_private_rubric_v1"]


class TaskSpec(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _normalize_input_requirements(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        requirements = data.get("input_requirements") or {}
        if not isinstance(requirements, dict):
            return data
        normalized = dict(data)
        for key in ("needs_data", "release", "dataset", "skim", "protocol", "max_files", "cache", "reuse_existing"):
            if key in requirements and key not in normalized:
                normalized[key] = requirements[key]
        if "sample" in requirements and "skim" not in normalized:
            normalized["skim"] = requirements["sample"]
        return normalized

    # identity
    id: str
    type: str
    mode: Literal["mock", "call_white"] = "mock"

    # execution/data requirements
    needs_data: bool = True
    input_requirements: dict[str, Any] = Field(default_factory=dict)
    release: str = "2025e-13tev-beta"
    dataset: str = "data"
    skim: Optional[str] = None
    protocol: str = "https"
    max_files: int = 3
    cache: bool = True
    reuse_existing: bool = True

    # Task directory containing task_spec.yaml and public contract files.
    spec_dir: Optional[str] = None

    solver_prompt_path: Optional[str] = "solver_prompt.md"
    submission_contract_path: Optional[str] = "submission_contract.yaml"

    # (optional) task description & constraints
    description: Optional[str] = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    level: Optional[str] = None

    # Capability-driven execution routing
    input_strategy: Literal["download", "shared_manifest"] = "download"
    solver_response_mode: Literal["submission_bundle_v1"] = "submission_bundle_v1"
    solver_backend: Optional[str] = None
    solver_model: Optional[str] = None
    evaluation_mode: EvaluationMode = "directory_contract_and_private_rubric_v1"

    # Task capabilities and defaults for large-input tasks.
    requires_large_input_data: bool = False
    supports_scenario_shared_input: bool = False
    supports_local_shared_input: bool = False

    def resolve_path(self, rel: str | None) -> Optional[Path]:
        if not rel:
            return None
        if self.spec_dir is None:
            return None
        p = Path(self.spec_dir) / rel
        return p


class TaskRuntimeOverride(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[Literal["mock", "call_white"]] = None
    input_strategy: Optional[Literal["download", "shared_manifest"]] = None
    max_files: Optional[int] = None
    reuse_existing: Optional[bool] = None
    cache: Optional[bool] = None
    release: Optional[str] = None
    dataset: Optional[str] = None
    skim: Optional[str] = None
    solver_backend: Optional[str] = None
    solver_model: Optional[str] = None


class GreenConfig(BaseModel):
    data_dir: str = "/tmp/atlas_data_cache"
    task_dirs: list[str] = Field(default_factory=lambda: ["tasks_public/t001_zpeak_fit"])
    solver_backend: str = "agent_1_oh"
    solver_model: Optional[str] = None
    input_access_mode: Optional[Literal["scenario_shared_mount", "local_shared_mount"]] = None
    shared_input_dir: Optional[str] = None
    input_manifest_path: Optional[str] = None
    allow_green_download: bool = False
    solver_request_timeout_seconds: Optional[int] = Field(default=None, ge=1)
    persist_payloads: bool = True
    task_overrides: dict[str, TaskRuntimeOverride] = Field(default_factory=dict)


def load_task_spec(spec_dir: str | Path) -> TaskSpec:
    spec_dir = str(spec_dir)
    path = Path(spec_dir) / "task_spec.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    require_valid(validate_task_spec_document(data), label=str(path))
    require_valid(validate_task_package_dir(spec_dir, require_manifest=False), label=str(Path(spec_dir)))

    # Inject spec_dir so loaders can resolve public contract files.
    data.setdefault("spec_dir", spec_dir)

    return TaskSpec.model_validate(data)
