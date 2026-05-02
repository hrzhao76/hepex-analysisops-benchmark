from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from tasks.task_spec import GreenConfig, TaskSpec
from utils import _safe_write_json


class InputAccessError(RuntimeError):
    pass


def resolve_input_access(task: TaskSpec, cfg: GreenConfig) -> Optional[Dict[str, Any]]:
    """Resolve static shared-input access for large-input tasks.

    The benchmark may only hand a path to the solver if that path is already
    shared by the scenario or local compose topology. This helper validates the
    configured shared path and writes a small manifest for solver-side discovery.
    """
    if not getattr(task, "requires_large_input_data", False):
        return None

    mode = cfg.input_access_mode
    shared_input_dir = cfg.shared_input_dir
    input_manifest_path = cfg.input_manifest_path

    if not mode:
        raise InputAccessError(
            f"Task {task.id} requires large input data, but no input_access_mode was provided."
        )
    if mode == "scenario_shared_mount" and not getattr(task, "supports_scenario_shared_input", False):
        raise InputAccessError(f"Task {task.id} does not support scenario_shared_mount.")
    if mode == "local_shared_mount" and not getattr(task, "supports_local_shared_input", False):
        raise InputAccessError(f"Task {task.id} does not support local_shared_mount.")
    if not shared_input_dir:
        raise InputAccessError(f"Task {task.id} requires shared_input_dir in runtime config.")
    if not input_manifest_path:
        raise InputAccessError(f"Task {task.id} requires input_manifest_path in runtime config.")
    if cfg.allow_green_download:
        raise InputAccessError(
            "allow_green_download is not supported for shared-input tasks; "
            "the shared mount must be provisioned by the scenario or local compose topology."
        )

    shared_dir = Path(shared_input_dir)
    if not shared_dir.exists() or not shared_dir.is_dir():
        raise InputAccessError(f"Shared input directory does not exist: {shared_dir}")

    files = []
    for path in sorted(shared_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name == Path(input_manifest_path).name:
            continue
        files.append(
            {
                "logical_name": path.name,
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "format": path.suffix.lower().lstrip(".") or "unknown",
            }
        )

    manifest_path = Path(input_manifest_path)
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
