from __future__ import annotations
from typing import Literal, Union
from pydantic import BaseModel, Field

class ZPeakFitTaskSpec(BaseModel):
    id: str = "t001_zpeak_fit"
    type: Literal["zpeak_fit"] = "zpeak_fit"

    needs_data: bool = True
    dataset: str = "data"
    skim: str = "2muons"
    protocol: str = "https"
    cache: bool = True
    max_files: int = 3

    workflow_spec_path: str = "specs/zpeak_fit/workflow.yaml"
    rubric_path: str = "specs/zpeak_fit/rubric.yaml"
    judge_prompt_path: str = "specs/zpeak_fit/judge_prompt.md"

    mode: Literal["mock", "call_white"] = "mock"

class HyyAnalysisTaskSpec(BaseModel):
    id: str = "t002_hyy"
    type: Literal["hyy_analysis"] = "hyy_analysis"

    needs_data: bool = True
    dataset: str = "data"
    skim: str = "2photons"
    protocol: str = "https"
    cache: bool = True
    max_files: int = 3

    workflow_spec_path: str = "specs/hyy/workflow.yaml"
    rubric_path: str = "specs/hyy/rubric.yaml"
    judge_prompt_path: str = "specs/hyy/judge_prompt.md"

    mode: Literal["mock", "call_white"] = "mock"

TaskSpec = Union[ZPeakFitTaskSpec, HyyAnalysisTaskSpec]

class GreenConfig(BaseModel):
    data_dir: str = "/tmp/atlas_data_cache"
    release: str = "2025e-13tev-beta"
    tasks: list[TaskSpec] = Field(default_factory=lambda: [ZPeakFitTaskSpec(), HyyAnalysisTaskSpec()])
