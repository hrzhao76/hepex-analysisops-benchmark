# src/engine/package_loader.py
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, TypedDict

import yaml


class SpecBundle(TypedDict):
    rubric: Dict[str, Any]
    eval_ref: Dict[str, Any]
    judge_prompt: Optional[str]   # None if not needed or not present
    white_prompt: Optional[str]   # None if missing (V1 alias)
    solver_prompt: Optional[str]  # V2: preferred prompt field


def _read_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _resolve_path(spec_dir: str | Path, maybe_path: str) -> Path:
    p = Path(maybe_path)
    if p.is_absolute():
        return p
    return Path(spec_dir) / p


def _has_llm_checks(rubric: Dict[str, Any]) -> bool:
    llm_checks = rubric.get("llm_checks", None)
    return isinstance(llm_checks, list) and len(llm_checks) > 0


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """Get attribute from object, supporting both Pydantic models and dicts."""
    val = getattr(obj, key, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def load_spec_bundle(task: Any) -> SpecBundle:
    """Load the V1 private spec bundle (rubric + eval_ref + judge_prompt + prompts).

    For V2 tasks_public/ tasks, rubric_path / eval_ref_path / judge_prompt_path
    will be None. In that case the corresponding bundle fields are returned as
    empty / None rather than raising. Private eval falls back gracefully.
    """
    spec_dir = _safe_get(task, "spec_dir")

    rubric_rel = _safe_get(task, "rubric_path", None)
    prompt_rel = _safe_get(task, "judge_prompt_path", None)
    eval_ref_rel = _safe_get(task, "eval_ref_path", None)
    white_prompt_rel = _safe_get(task, "white_prompt_path", None)

    # rubric — required for private eval, but optional in public-safe tasks
    rubric: Dict[str, Any] = {}
    if spec_dir and rubric_rel:
        rubric_path = _resolve_path(spec_dir, rubric_rel)
        if rubric_path.exists():
            rubric = _read_yaml(rubric_path)

    # eval_ref — optional always
    eval_ref: Dict[str, Any] = {}
    if spec_dir and eval_ref_rel:
        p = _resolve_path(spec_dir, eval_ref_rel)
        if p.exists():
            eval_ref = _read_yaml(p)

    # judge_prompt — only if llm_checks exist and spec_dir is available
    judge_prompt: Optional[str] = None
    if spec_dir and _has_llm_checks(rubric) and prompt_rel:
        p = _resolve_path(spec_dir, prompt_rel)
        if p.exists():
            judge_prompt = _read_text(p)

    # white_prompt (V1 alias) — optional, do NOT require
    white_prompt: Optional[str] = None
    if spec_dir and white_prompt_rel:
        p = _resolve_path(spec_dir, white_prompt_rel)
        if p.exists():
            white_prompt = _read_text(p)

    # solver_prompt (V2) — resolved separately via load_solver_prompt()
    return {
        "rubric": rubric,
        "eval_ref": eval_ref,
        "judge_prompt": judge_prompt,
        "white_prompt": white_prompt,
        "solver_prompt": None,  # populated by load_solver_prompt() if needed
    }


def load_solver_prompt(task: Any) -> Optional[str]:
    """Load the public solver prompt for a task.

    Resolution order (V2-first):
      1. solver_prompt_path  (V2: tasks_public/<task>/solver_prompt.md)
      2. white_prompt_path   (V1 compat alias)
      3. None if neither found
    """
    spec_dir = _safe_get(task, "spec_dir")

    # Try V2 solver_prompt_path first
    solver_prompt_rel = _safe_get(task, "solver_prompt_path", None)
    if solver_prompt_rel and spec_dir:
        p = _resolve_path(spec_dir, solver_prompt_rel)
        if p.exists():
            return _read_text(p)

    # Fallback to V1 white_prompt_path
    white_prompt_rel = _safe_get(task, "white_prompt_path", None)
    if white_prompt_rel and spec_dir:
        p = _resolve_path(spec_dir, white_prompt_rel)
        if p.exists():
            return _read_text(p)

    return None
