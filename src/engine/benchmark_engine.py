from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Protocol

from tasks.task_spec import GreenConfig, TaskRuntimeOverride, TaskSpec, load_task_spec
from utils import _new_run_id, _safe_write_json, _safe_write_text, _utc_now_iso
from utils.atlas_download import ensure_atlas_open_data_downloaded
from utils.mock_traces import get_mock_bundle

from .evaluation import EvaluationEngine
from .input_access import InputAccessError, resolve_input_access, resolve_shared_input_paths
from .package_loader import load_solver_prompt, load_submission_contract
from .prompt_render import _builtin_minimal_prompt
from .run_models import EvalRequest
from .submission_bundle import (
    SubmissionBundleError,
    materialize_submission_bundle,
    parse_submission_bundle,
)


CONTRACT_EVALUATION_MODES = {
    "directory_contract_and_private_l1",
    "directory_contract_and_private_rubric_v1",
}


class SolverTransport(Protocol):
    async def request_submission_bundle(self, payload: dict[str, Any]) -> str:
        ...


class RunObserver(Protocol):
    async def status(self, text: str) -> None:
        ...

    async def task_result(self, name: str, summary: str, report: dict[str, Any]) -> None:
        ...

    async def summary(self, text: str, overall: dict[str, Any]) -> None:
        ...


@dataclass
class BenchmarkRunResult:
    done_text: str
    overall: dict[str, Any]


class BenchmarkEngine:
    def __init__(
        self,
        *,
        evaluation_engine: Optional[EvaluationEngine] = None,
        task_loader=load_task_spec,
    ) -> None:
        self.evaluation_engine = evaluation_engine or EvaluationEngine()
        self.task_loader = task_loader

    @staticmethod
    def _resolve_data_dir(cfg: GreenConfig) -> str:
        env_dir = os.getenv("HEPEX_DATA_DIR")
        if getattr(cfg, "data_dir", "").strip():
            return cfg.data_dir
        if env_dir and env_dir.strip():
            return env_dir
        return cfg.data_dir

    @staticmethod
    def _runs_root(base_data_dir: str) -> Path:
        return Path(base_data_dir) / "runs"

    @staticmethod
    def _task_eval_dir(runs_root: Path, run_id: str, task_id: str) -> Path:
        return runs_root / run_id / task_id

    @staticmethod
    def _has_runtime_shared_input(cfg: GreenConfig) -> bool:
        return bool(cfg.input_access_mode and cfg.shared_input_dir)

    @staticmethod
    def _shared_root_files(shared_dir: Path | None) -> list[Path]:
        if shared_dir is None:
            return []
        if not shared_dir.exists() or not shared_dir.is_dir():
            return []
        return sorted(path for path in shared_dir.iterdir() if path.is_file() and path.suffix.lower() == ".root")

    @staticmethod
    def _green_download_summary(download_info: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if download_info is None:
            return None
        keys = [
            "download_skipped",
            "reason",
            "release",
            "dataset",
            "skim",
            "protocol",
            "output_dir",
            "n_requested",
            "n_ok",
            "n_fail",
            "n_existing_root_files",
        ]
        return {key: download_info[key] for key in keys if key in download_info}

    async def _ensure_green_shared_input(
        self,
        task: TaskSpec,
        cfg: GreenConfig,
        task_eval_dir: Path,
        observer: RunObserver,
    ) -> Optional[dict[str, Any]]:
        if not cfg.allow_green_download:
            return None
        if not getattr(task, "skim", None):
            raise InputAccessError(f"Task {task.id} requested Green-managed download but no skim/sample is configured.")

        _, shared_dir, _ = resolve_shared_input_paths(task, cfg)
        existing_roots = self._shared_root_files(shared_dir)
        requested_files = getattr(task, "max_files", 0) or 0
        enough_existing = bool(existing_roots) and (requested_files <= 0 or len(existing_roots) >= requested_files)
        if getattr(task, "reuse_existing", True) and enough_existing:
            return {
                "download_skipped": True,
                "reason": "shared_input_already_has_enough_root_files",
                "n_existing_root_files": len(existing_roots),
                "output_dir": str(shared_dir),
            }

        await observer.status(
            (
                f"[{task.id}] Green downloading shared input: "
                f"{task.release}/{task.dataset}/{task.skim} (max_files={requested_files})."
            )
        )
        workers = int(os.environ.get("HEPEX_GREEN_DOWNLOAD_WORKERS", "6"))
        download_info = ensure_atlas_open_data_downloaded(
            skim=str(task.skim),
            release=task.release,
            dataset=task.dataset,
            protocol=task.protocol,
            output_dir=str(shared_dir),
            max_files=requested_files,
            workers=workers,
            verbose=True,
        )
        _safe_write_json(shared_dir / "green_download_manifest.json", download_info)
        _safe_write_json(task_eval_dir / "green_download_manifest.json", download_info)

        if int(download_info.get("n_requested") or 0) <= 0:
            raise InputAccessError(f"Green downloader found no input files for task {task.id}.")
        if int(download_info.get("n_ok") or 0) <= 0 or int(download_info.get("n_fail") or 0) > 0:
            raise InputAccessError(
                (
                    f"Green downloader failed for task {task.id}: "
                    f"n_ok={download_info.get('n_ok')} n_fail={download_info.get('n_fail')}."
                )
            )
        return download_info

    @staticmethod
    def _extract_json_from_response(text: str) -> str:
        code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
        if code_block_match:
            return code_block_match.group(1).strip()

        start = text.find("{")
        if start >= 0:
            depth = 0
            in_string = False
            escape = False
            for idx, ch in enumerate(text[start:], start):
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start : idx + 1]
        return text

    @staticmethod
    def _raw_response_metadata(response_str: str, *, path: Optional[str] = None) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "raw_response_preview": response_str[:1000],
            "raw_response_length": len(response_str),
        }
        if path:
            metadata["raw_response_path"] = path
        return metadata

    @staticmethod
    def _public_task_view(task: TaskSpec) -> dict[str, Any]:
        return task.model_dump(exclude_none=True)

    @staticmethod
    def _task_override_payload(override: TaskRuntimeOverride) -> dict[str, Any]:
        return override.model_dump(exclude_none=True)

    @staticmethod
    def _persisted_eval_request_payload(request: EvalRequest) -> dict[str, Any]:
        payload = request.model_dump(mode="json", exclude_none=True)
        config = payload.get("config")
        if (
            isinstance(config, dict)
            and payload.get("solver_backend") is not None
            and config.get("solver_backend") == payload.get("solver_backend")
        ):
            payload.pop("solver_backend", None)
        return payload

    def _apply_task_runtime_override(
        self,
        task: TaskSpec,
        cfg: GreenConfig,
    ) -> tuple[Optional[TaskSpec], dict[str, Any]]:
        override = (cfg.task_overrides or {}).get(task.id)
        if override is None:
            return task, {}

        applied = self._task_override_payload(override)
        if applied.get("enabled") is False:
            return None, applied

        updates = {k: v for k, v in applied.items() if k != "enabled"}
        if not updates:
            return task, applied

        return TaskSpec.model_validate({**task.model_dump(), **updates}), applied

    def _validate_task_capabilities(self, task: TaskSpec, cfg: GreenConfig) -> None:
        if task.input_strategy == "shared_manifest":
            if not getattr(task, "needs_data", False):
                raise InputAccessError(
                    f"Task {task.id} uses input_strategy=shared_manifest but needs_data is false."
                )
            if not getattr(task, "requires_large_input_data", False):
                raise InputAccessError(
                    f"Task {task.id} uses input_strategy=shared_manifest but requires_large_input_data is false."
                )
            if not self._has_runtime_shared_input(cfg) and getattr(task, "mode", "mock") != "mock":
                raise InputAccessError(
                    f"Task {task.id} uses input_strategy=shared_manifest but runtime shared-input config is incomplete."
                )

        if task.solver_response_mode == "submission_bundle_v1" and not getattr(task, "submission_contract_path", None):
            raise SubmissionBundleError(
                f"Task {task.id} uses solver_response_mode=submission_bundle_v1 but has no submission_contract_path."
            )

        if task.evaluation_mode in CONTRACT_EVALUATION_MODES and not getattr(task, "submission_contract_path", None):
            raise SubmissionBundleError(
                f"Task {task.id} uses evaluation_mode={task.evaluation_mode} but has no submission_contract_path."
            )

    @staticmethod
    def _build_mock_input_manifest(task: TaskSpec, task_eval_dir: Path) -> dict[str, Any]:
        shared_dir = task_eval_dir / "mock_shared_input"
        shared_dir.mkdir(parents=True, exist_ok=True)

        root_path = shared_dir / "events.root"
        if not root_path.exists():
            _safe_write_text(root_path, "placeholder")

        manifest_path = shared_dir / "input_manifest.json"
        manifest = {
            "task_id": task.id,
            "release": getattr(task, "release", None),
            "dataset": getattr(task, "dataset", None),
            "skim": getattr(task, "skim", None),
            "shared_input_dir": str(shared_dir),
            "input_manifest_path": str(manifest_path),
            "files": [
                {
                    "logical_name": root_path.name,
                    "path": str(root_path),
                    "size_bytes": root_path.stat().st_size,
                }
            ],
            "read_only_for_solver": True,
            "input_access_mode": "local_shared_mount",
            "synthetic_for_mock_mode": True,
        }
        _safe_write_json(manifest_path, manifest)
        return manifest

    async def _prepare_task_input(
        self,
        task: TaskSpec,
        cfg: GreenConfig,
        task_eval_dir: Path,
        observer: RunObserver,
    ) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
        self._validate_task_capabilities(task, cfg)

        if not getattr(task, "needs_data", False):
            return None, None

        if task.input_strategy == "shared_manifest":
            if self._has_runtime_shared_input(cfg):
                download_info = await self._ensure_green_shared_input(task, cfg, task_eval_dir, observer)
                input_manifest = resolve_input_access(task, cfg)
            elif getattr(task, "mode", "mock") == "mock":
                download_info = None
                input_manifest = self._build_mock_input_manifest(task, task_eval_dir)
            else:
                raise InputAccessError(
                    f"Task {task.id} uses input_strategy=shared_manifest but runtime shared-input config is incomplete."
                )
            data_info = {
                "shared_input_dir": input_manifest.get("shared_input_dir"),
                "input_manifest_path": input_manifest.get("input_manifest_path"),
                "n_files": len(input_manifest.get("files", [])),
                "download_managed_by": "green" if cfg.allow_green_download else "scenario",
            }
            download_summary = self._green_download_summary(download_info)
            if download_summary is not None:
                data_info["download_summary"] = download_summary
            _safe_write_json(task_eval_dir / "data_info.json", data_info)
            await observer.status(f"[{task.id}] Shared input ready: {data_info['n_files']} files.")
            return data_info, input_manifest

        if task.input_strategy != "download":
            raise InputAccessError(f"Unsupported input_strategy for task {task.id}: {task.input_strategy}")

        data_info = {
            "release": task.release,
            "dataset": task.dataset,
            "skim": task.skim,
            "protocol": task.protocol,
            "max_files": task.max_files,
            "download_managed_by": "solver",
        }
        _safe_write_json(task_eval_dir / "data_info.json", data_info)
        await observer.status(
            f"[{task.id}] Delegating data download to solver: "
            f"{task.release}/{task.dataset}/{task.skim} (max_files={task.max_files})."
        )
        return data_info, None

    def _build_solver_payload(
        self,
        task: TaskSpec,
        input_manifest: dict[str, Any],
        solver_work_dir: Path,
        solver_backend: str,
    ) -> dict[str, Any]:
        contract = load_submission_contract(task)
        prompt = load_solver_prompt(task) or _builtin_minimal_prompt(task.id, task.type)
        prompt = prompt.replace("{{TASK_ID}}", task.id).replace("{{MAX_FILES}}", str(task.max_files))
        solver_work_dir_str = str(solver_work_dir)
        constraints = dict(getattr(task, "constraints", {}) or {})
        constraints.pop("solver_backend", None)
        constraints.pop("solver_agent", None)
        constraints.update(
            {
                "response_format": "submission_bundle_v1",
                "allow_purple_network": task.input_strategy == "download",
            }
        )

        return {
            "role": "task_request",
            "task_id": task.id,
            "task_type": task.type,
            "mode": getattr(task, "mode", "mock"),
            "level": getattr(task, "level", None),
            "solver_backend": solver_backend,
            "prompt": prompt,
            "submission_contract": contract,
            "data": {
                "release": task.release,
                "dataset": task.dataset,
                "skim": task.skim,
                "protocol": task.protocol,
                "max_files": task.max_files,
                "input_strategy": task.input_strategy,
                "shared_input_dir": input_manifest.get("shared_input_dir"),
                "input_manifest_path": input_manifest.get("input_manifest_path"),
                "work_dir": solver_work_dir_str,
                "output_dir": solver_work_dir_str,
                "read_only_for_solver": True,
            },
            "constraints": constraints,
        }

    async def _get_submission_bundle(
        self,
        task: TaskSpec,
        input_manifest: dict[str, Any],
        task_eval_dir: Path,
        persist_payloads: bool,
        solver_transport: SolverTransport,
        solver_backend: str,
    ) -> dict[str, Any]:
        if getattr(task, "mode", "mock") == "mock":
            bundle = get_mock_bundle(task.type, task.id)
            if bundle.get("status") == "error":
                raise SubmissionBundleError(bundle.get("error", f"Unknown mock bundle error for task {task.id}"))
            return bundle

        solver_work_dir = task_eval_dir / "solver_work"
        solver_work_dir.mkdir(parents=True, exist_ok=True)
        payload = self._build_solver_payload(task, input_manifest, solver_work_dir, solver_backend)
        if persist_payloads:
            _safe_write_json(task_eval_dir / "purple_request.json", payload)

        response_str = await solver_transport.request_submission_bundle(payload)
        if persist_payloads:
            _safe_write_text(task_eval_dir / "purple_response_raw.txt", response_str)

        try:
            return json.loads(self._extract_json_from_response(response_str))
        except json.JSONDecodeError as e:
            error = SubmissionBundleError(f"Purple agent returned non-JSON response: {e}")
            error.raw_response = response_str
            raise error from e

    async def _collect_solver_output(
        self,
        task: TaskSpec,
        task_eval_dir: Path,
        input_manifest: Optional[dict[str, Any]],
        persist_payloads: bool,
        solver_transport: SolverTransport,
        solver_backend: str,
    ) -> dict[str, Any]:
        if task.solver_response_mode != "submission_bundle_v1":
            raise SubmissionBundleError(
                f"Unsupported solver_response_mode for task {task.id}: {task.solver_response_mode}"
            )

        contract = load_submission_contract(task)
        try:
            raw_bundle = await self._get_submission_bundle(
                task,
                input_manifest or {},
                task_eval_dir,
                persist_payloads,
                solver_transport,
                solver_backend,
            )
            if persist_payloads:
                _safe_write_json(task_eval_dir / "submission_bundle_raw.json", raw_bundle)
            parsed_bundle = parse_submission_bundle(raw_bundle, contract)
            artifact_manifest = materialize_submission_bundle(parsed_bundle, contract, task_eval_dir)
            submission_trace = json.loads((task_eval_dir / "submission_trace.json").read_text(encoding="utf-8"))
            if persist_payloads:
                _safe_write_json(task_eval_dir / "artifact_manifest.json", artifact_manifest)
            return {
                "submission_trace": submission_trace,
                "artifact_manifest": artifact_manifest,
                "submission_bundle_raw": raw_bundle,
            }
        except Exception as e:
            submission_trace = {
                "task_id": task.id,
                "status": "error",
                "error": f"Failed to get submission bundle: {type(e).__name__}: {e}",
            }
            if isinstance(e, SubmissionBundleError) and getattr(e, "raw_response", None):
                submission_trace.update(
                    self._raw_response_metadata(
                        e.raw_response,
                        path="purple_response_raw.txt" if persist_payloads else None,
                    )
                )
            _safe_write_json(task_eval_dir / "submission_trace.json", submission_trace)
            return {"submission_trace": submission_trace}

    async def run(
        self,
        request: EvalRequest,
        solver_transport: SolverTransport,
        observer: RunObserver,
    ) -> BenchmarkRunResult:
        config_payload = dict(request.config)
        if request.solver_backend:
            config_payload["solver_backend"] = request.solver_backend
        cfg = GreenConfig.model_validate(config_payload)
        await observer.status(f"Received config: {cfg}")
        await observer.status(f"Solver backend default: {cfg.solver_backend}")

        base_data_dir = self._resolve_data_dir(cfg)
        run_id = _new_run_id()
        runs_root = self._runs_root(base_data_dir)
        run_dir = runs_root / run_id
        runs_root.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(parents=True, exist_ok=True)

        await observer.status("Starting tasks...")

        task_runs: list[tuple[TaskSpec, dict[str, Any]]] = []
        for task_dir in cfg.task_dirs:
            loaded = self.task_loader(task_dir)
            effective_task, applied_overrides = self._apply_task_runtime_override(loaded, cfg)
            if effective_task is None:
                await observer.status(f"[{loaded.id}] Skipped by config.task_overrides.")
                continue
            task_runs.append((effective_task, applied_overrides))

        overall: dict[str, Any] = {
            "run_id": run_id,
            "run_dir": str(run_dir.resolve()),
            "data_dir": os.path.abspath(base_data_dir),
            "tasks": [],
            "score_total": 0.0,
            "score_max": float(len(task_runs)),
        }
        if cfg.persist_payloads:
            _safe_write_json(run_dir / "eval_request.json", self._persisted_eval_request_payload(request))
            _safe_write_json(run_dir / "green_config.json", cfg.model_dump(mode="json", exclude_none=True))

        for idx, (task, applied_overrides) in enumerate(task_runs, start=1):
            task_eval_dir = self._task_eval_dir(runs_root, run_id, task.id)
            task_eval_dir.mkdir(parents=True, exist_ok=True)
            solver_backend = task.solver_backend or cfg.solver_backend

            meta = {
                "timestamp": _utc_now_iso(),
                "task_id": task.id,
                "task_type": task.type,
                "mode": getattr(task, "mode", "mock"),
                "release": getattr(task, "release", None),
                "dataset": getattr(task, "dataset", None),
                "skim": getattr(task, "skim", None),
                "protocol": getattr(task, "protocol", None),
                "max_files": getattr(task, "max_files", None),
                "reuse_existing": getattr(task, "reuse_existing", None),
                "solver_backend": solver_backend,
                "solver_work_dir": str((task_eval_dir / "solver_work").resolve()),
                "task_overrides_applied": applied_overrides,
            }
            _safe_write_json(task_eval_dir / "meta.json", meta)

            await observer.status(f"Task {idx}/{len(task_runs)}: {task.type} ({task.id})")

            try:
                data_info, input_manifest = await self._prepare_task_input(
                    task,
                    cfg,
                    task_eval_dir,
                    observer,
                )
            except (InputAccessError, SubmissionBundleError) as e:
                task_report = {
                    "task_id": task.id,
                    "type": task.type,
                    "status": "error",
                    "error": str(e),
                    "task_overrides_applied": applied_overrides,
                    "final": {"total_score": 0.0, "max_score": 1.0, "normalized_score": 0.0},
                }
                overall["tasks"].append(task_report)
                await observer.task_result(f"Result-{task.id}", f"[{task.id}] ERROR: {e}", task_report)
                continue
            except Exception as e:
                task_report = {
                    "task_id": task.id,
                    "type": task.type,
                    "status": "error",
                    "error": f"Data preparation failed: {type(e).__name__}: {e}",
                    "task_overrides_applied": applied_overrides,
                    "final": {"total_score": 0.0, "max_score": 1.0, "normalized_score": 0.0},
                }
                overall["tasks"].append(task_report)
                await observer.task_result(f"Result-{task.id}", f"[{task.id}] ERROR: data preparation failed.", task_report)
                continue

            collected = await self._collect_solver_output(
                task,
                task_eval_dir,
                input_manifest,
                cfg.persist_payloads,
                solver_transport,
                solver_backend,
            )

            judge_input = {
                "task_spec": self._public_task_view(task),
                "data_info": data_info,
                "submission_trace": {"path": "submission_trace.json"},
            }
            _safe_write_json(task_eval_dir / "judge_input.json", judge_input)

            try:
                report = self.evaluation_engine.evaluate_submission(task, task_eval_dir)
            except Exception as e:
                err_text = f"{type(e).__name__}: {e}"
                _safe_write_text(task_eval_dir / "engine_error.txt", err_text)
                report = {
                    "task_id": task.id,
                    "type": task.type,
                    "status": "error",
                    "error": f"Engine failed: {err_text}",
                    "task_overrides_applied": applied_overrides,
                    "final": {"total_score": 0.0, "max_score": 1.0, "normalized_score": 0.0},
                }

            report["task_id"] = task.id
            report["type"] = task.type
            report["task_overrides_applied"] = applied_overrides

            final = report.setdefault("final", {})
            total_score = float(final.get("total_score", 0.0))
            max_score = float(final.get("max_score", 100.0))
            normalized = total_score / max(1e-9, max_score)

            final["total_score"] = total_score
            final["max_score"] = max_score
            final["normalized_score"] = normalized

            overall["score_total"] += normalized
            overall["tasks"].append(report)

            _safe_write_json(task_eval_dir / "judge_output.json", report)

            meta.update(
                {
                    "score_total": total_score,
                    "score_max": max_score,
                    "normalized_score": normalized,
                    "finished_at": _utc_now_iso(),
                    "status": report.get("status", "ok"),
                }
            )
            _safe_write_json(task_eval_dir / "meta.json", meta)

            summary = f"[{task.id}] {task.type}: score={total_score:.2f}/{max_score:.2f} (norm={normalized:.3f})"
            await observer.task_result(f"Result-{task.id}", summary, report)

        done_text = (
            f"Done. Normalized score: {overall['score_total']:.3f}/{overall['score_max']:.3f}\n"
            f"run_id={overall['run_id']}\n"
            f"run_dir={overall['run_dir']}"
        )
        _safe_write_json(run_dir / "run_summary.json", overall)
        await observer.summary(done_text, overall)
        return BenchmarkRunResult(done_text=done_text, overall=overall)
