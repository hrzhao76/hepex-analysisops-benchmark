from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from tasks.task_spec import GreenConfig, TaskSpec
from utils import _safe_write_json


class InputAccessError(RuntimeError):
    pass


def _task_samples(task: TaskSpec) -> list[dict[str, Any]]:
    requirements = getattr(task, "input_requirements", {}) or {}
    samples = requirements.get("samples")
    if isinstance(samples, list):
        return samples
    legacy_groups = requirements.get("sample_groups", [])
    return legacy_groups if isinstance(legacy_groups, list) else []


def _template_context(task: TaskSpec) -> Dict[str, Any]:
    return {
        "task_id": task.id,
        "task_type": task.type,
        "level": getattr(task, "level", None) or "",
        "release": getattr(task, "release", None) or "",
        "dataset": getattr(task, "dataset", None) or "",
        "skim": getattr(task, "skim", None) or "",
        "sample": getattr(task, "skim", None) or "",
        "protocol": getattr(task, "protocol", None) or "",
    }


def _render_template(value: str, context: Dict[str, Any], *, field_name: str, task_id: str) -> str:
    try:
        return value.format(**context)
    except KeyError as exc:
        missing = exc.args[0]
        raise InputAccessError(
            f"Task {task_id} {field_name} template references unknown field {{{missing}}}."
        ) from exc


def resolve_shared_input_paths(task: TaskSpec, cfg: GreenConfig) -> tuple[str, Path, Path]:
    mode = cfg.input_access_mode
    if not mode:
        raise InputAccessError(
            f"Task {task.id} requires large input data, but no input_access_mode was provided."
        )
    if mode == "scenario_shared_mount" and not getattr(task, "supports_scenario_shared_input", False):
        raise InputAccessError(f"Task {task.id} does not support scenario_shared_mount.")
    if mode == "local_shared_mount" and not getattr(task, "supports_local_shared_input", False):
        raise InputAccessError(f"Task {task.id} does not support local_shared_mount.")
    if not cfg.shared_input_dir:
        raise InputAccessError(f"Task {task.id} requires shared_input_dir in runtime config.")

    context = _template_context(task)
    shared_input_dir = _render_template(
        cfg.shared_input_dir,
        context,
        field_name="shared_input_dir",
        task_id=task.id,
    )
    input_manifest_path = (
        _render_template(
            cfg.input_manifest_path,
            context,
            field_name="input_manifest_path",
            task_id=task.id,
        )
        if cfg.input_manifest_path
        else str(Path(shared_input_dir) / "input_manifest.json")
    )
    return mode, Path(shared_input_dir), Path(input_manifest_path)


def resolve_input_access(task: TaskSpec, cfg: GreenConfig) -> Optional[Dict[str, Any]]:
    """Resolve static shared-input access for large-input tasks.

    The benchmark may only hand a path to the solver if that path is already
    shared by the scenario or local compose topology. This helper validates the
    configured shared path and writes a small manifest for solver-side discovery.
    """
    if not getattr(task, "requires_large_input_data", False):
        return None

    mode, shared_dir, manifest_path = resolve_shared_input_paths(task, cfg)
    if not shared_dir.exists() or not shared_dir.is_dir():
        raise InputAccessError(f"Shared input directory does not exist: {shared_dir}")

    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InputAccessError(f"Input manifest is not valid JSON: {manifest_path}") from exc
        if isinstance(manifest, dict) and (
            isinstance(manifest.get("samples"), list) or isinstance(manifest.get("sample_groups"), list)
        ):
            return manifest

    if _task_samples(task):
        raise InputAccessError(
            f"Task {task.id} declares multiple samples, but no multi-sample input manifest exists at {manifest_path}."
        )

    files = []
    for path in sorted(shared_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name == manifest_path.name:
            continue
        if path.suffix.lower() != ".root":
            continue
        files.append(
            {
                "logical_name": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "format": path.suffix.lower().lstrip(".") or "unknown",
            }
        )

    manifest = {
        "task_id": task.id,
        "release": getattr(task, "release", None),
        "dataset": getattr(task, "dataset", None),
        "skim": getattr(task, "skim", None),
        "shared_input_dir": str(shared_dir),
        "input_manifest_path": str(manifest_path),
        "files": files[: getattr(task, "max_files", len(files)) or len(files)],
        "read_only_for_solver": True,
        "input_access_mode": mode,
    }
    _safe_write_json(manifest_path, manifest)
    return manifest
