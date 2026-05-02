from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _read_yaml(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _resolve_path(spec_dir: str | Path, maybe_path: str) -> Path:
    p = Path(maybe_path)
    if p.is_absolute():
        return p
    return Path(spec_dir) / p


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    val = getattr(obj, key, None)
    if val is not None:
        return val
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def load_solver_prompt(task: Any) -> Optional[str]:
    """Load the public solver prompt for a tasks_public task."""
    spec_dir = _safe_get(task, "spec_dir")
    prompt_rel = _safe_get(task, "solver_prompt_path", "solver_prompt.md")
    if not spec_dir or not prompt_rel:
        return None
    path = _resolve_path(spec_dir, prompt_rel)
    if not path.exists():
        return None
    return _read_text(path)


def load_submission_contract(task: Any) -> Dict[str, Any]:
    """Load the public submission contract for a task."""
    spec_dir = _safe_get(task, "spec_dir")
    contract_rel = _safe_get(task, "submission_contract_path", "submission_contract.yaml")
    if not spec_dir or not contract_rel:
        return {}
    path = _resolve_path(spec_dir, contract_rel)
    if not path.exists():
        return {}
    return _read_yaml(path)


def load_private_l1_rubric(task: Any, secret_store: Any) -> Dict[str, Any]:
    """Load a private L1 rubric from the secret store if available."""
    if secret_store is None:
        return {}
    task_id = _safe_get(task, "id")
    contract = load_submission_contract(task)
    contract_hash = secret_store.contract_hash(contract) if contract else None
    return secret_store.get_task_private_rubric(task_id, public_contract_hash=contract_hash)
