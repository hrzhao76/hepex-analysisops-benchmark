from __future__ import annotations

import os
import shutil
from typing import Any, Optional
import json
import logging

from pydantic import BaseModel, HttpUrl, ValidationError
from a2a.server.tasks import TaskUpdater
from a2a.types import Message, TaskState, Part, TextPart, DataPart
from a2a.utils import get_message_text, new_agent_text_message

from messenger import Messenger
from tasks.task_spec import GreenConfig, TaskSpec, load_task_spec

from utils import _utc_now_iso, _new_run_id, _safe_write_json, _safe_write_text
from utils.atlas_download import ensure_atlas_open_data_downloaded  
from engine.package_loader import load_spec_bundle, load_solver_prompt
from engine.prompt_render import _builtin_minimal_prompt
from engine.evaluator import evaluate_task
from engine.llm_judge_gemini import GeminiJudge

from utils.mock_traces import get_mock_trace
from dotenv import load_dotenv, find_dotenv
from pathlib import Path


logger = logging.getLogger(__name__)

class EvalRequest(BaseModel):
    participants: dict[str, HttpUrl]  # role -> agent URL
    config: dict[str, Any]


class Agent:
    required_roles: list[str] = []  # later: ["white_agent"]

    def __init__(self):
        load_dotenv(find_dotenv())
        self.messenger = Messenger()
        try:
            self.gemini_judge = GeminiJudge()
        except RuntimeError:
            # OK if key missing, assuming run() won't need it or will fail gracefully
            self.gemini_judge = None

    def validate_request(self, request: EvalRequest) -> tuple[bool, str]:
        missing_roles = set(self.required_roles) - set(request.participants.keys())
        if missing_roles:
            return False, f"Missing roles: {sorted(missing_roles)}"
        return True, "ok"

    def _resolve_data_dir(self, cfg: GreenConfig) -> str:
        """
        Precedence:
        1) cfg.data_dir if non-empty
        2) env HEPEX_DATA_DIR if set
        3) fallback to cfg.data_dir default (already set)
        """
        env_dir = os.getenv("HEPEX_DATA_DIR")
        if getattr(cfg, "data_dir", "").strip():
            return cfg.data_dir
        if env_dir and env_dir.strip():
            return env_dir
        return cfg.data_dir  # default

    def _task_data_dir(self, base_dir: str, task: TaskSpec) -> Path:
        # input ROOT cache
        return Path(base_dir) / task.release / task.dataset / task.skim

    
    def _runs_root(self, base_data_dir: str) -> Path:
        return Path(base_data_dir) / "runs"

    def _task_eval_dir(self, runs_root: Path, run_id: str, task_id: str) -> Path:
        return runs_root / run_id / task_id
    

    async def _get_submission_trace(
        self,
        task: TaskSpec,
        request: EvalRequest,
        data_info: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        mode = getattr(task, "mode", "mock")

        if mode == "mock":
            return get_mock_trace(task.type, task.id)

        # Future: call white agent
        # return {"task_id": task.id, "status": "error", "error": "call_white not implemented yet"}

        # ---- call_white path ----
        # V2: use load_solver_prompt() which resolves solver_prompt.md first,
        # then falls back to white_prompt.md (V1 compat).
        prompt = load_solver_prompt(task) or _builtin_minimal_prompt(task.id, task.type)

        # optional: simple templating
        prompt = (
            prompt
            .replace("{{TASK_ID}}", task.id)
            .replace("{{MAX_FILES}}", str(task.max_files))
        )

        # 2) prepare data payload
        files = []
        if data_info:
            # adapt this key if needed
            files = data_info.get("local_paths", [])

        payload = {
            "role": "task_request",
            "task_id": task.id,
            "task_type": task.type,
            "prompt": prompt,
            "data": {
                "files": files[: task.max_files],
                "release": task.release,
                "dataset": task.dataset,
                "skim": task.skim,
            },
            "constraints": getattr(task, "constraints", {}),
        }

        message_str = json.dumps(payload, indent=2)

        # 3) send to white agent
        white_url = str(request.participants["white_agent"])

        response_str = await self.messenger.talk_to_agent(
            message=message_str,
            url=white_url,
            new_conversation=True,   # IMPORTANT: new task = new conversation
        )

        # 4) parse response - handle markdown code blocks
        def extract_json_from_response(text: str) -> str:
            """Extract JSON from response, handling markdown code blocks."""
            # Try to find JSON in markdown code block
            import re
            # Match ```json...``` or ```...``` blocks
            code_block_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', text)
            if code_block_match:
                return code_block_match.group(1).strip()
            # Try to find raw JSON object
            json_match = re.search(r'(\{[\s\S]*\})', text)
            if json_match:
                return json_match.group(1)
            return text
        
        try:
            json_text = extract_json_from_response(response_str)
            submission_trace = json.loads(json_text)
        except json.JSONDecodeError as e:
            return {
                "task_id": task.id,
                "status": "error",
                "error": f"White agent returned non-JSON response: {e}",
                "raw_response": response_str[:1000],
            }

        return submission_trace


    async def run(self, message: Message, updater: TaskUpdater) -> None:
        input_text = get_message_text(message)

        # 1) Parse platform request
        try:
            request: EvalRequest = EvalRequest.model_validate_json(input_text)
            ok, msg = self.validate_request(request)
            # update, show received request
            logger.info(f"Received request: {request}")
            await updater.update_status(TaskState.working, new_agent_text_message(f"Received request: {request}"))
            if not ok:
                await updater.reject(new_agent_text_message(msg))
                return
        except ValidationError as e:
            await updater.reject(new_agent_text_message(f"Invalid request: {e}"))
            return

        # 2) Parse green config
        try:
            cfg = GreenConfig.model_validate(request.config)
            # update, show received config
            logger.info(f"Received config: {cfg}")
            await updater.update_status(TaskState.working, new_agent_text_message(f"Received config: {cfg}"))
            
        except ValidationError as e:
            await updater.reject(new_agent_text_message(f"Invalid config: {e}"))
            return

        base_data_dir = self._resolve_data_dir(cfg)

        run_id = _new_run_id()
        runs_root = self._runs_root(base_data_dir)
        runs_root.mkdir(parents=True, exist_ok=True)

        await updater.update_status(TaskState.working, new_agent_text_message("Starting tasks..."))

        overall: dict[str, Any] = {
            "run_id": run_id,                              
            "run_dir": str((runs_root / run_id).resolve()),
            "data_dir": os.path.abspath(base_data_dir),
            "tasks": [],
            "score_total": 0.0,                 # sum of normalized per task
            "score_max": float(len(cfg.task_dirs)), # maximum normalized sum
        }

        # 3) Run tasks sequentially
        task_specs = [load_task_spec(d) for d in cfg.task_dirs]
        for idx, task in enumerate(task_specs, start=1):
            task_eval_dir = self._task_eval_dir(runs_root, run_id, task.id)  
            task_eval_dir.mkdir(parents=True, exist_ok=True)                

            # NEW: meta skeleton (write early so crash still leaves trace)
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
            }
            _safe_write_json(task_eval_dir / "meta.json", meta)

            await updater.update_status(
                TaskState.working,
                new_agent_text_message(f"Task {idx}/{len(cfg.task_dirs)}: {task.type} ({task.id})"),
            )
            logger.info(f"Starting Task {idx}/{len(cfg.task_dirs)}: {task.type} ({task.id})")

            # 3a) Ensure data (optional)
            data_info: Optional[dict[str, Any]] = None
            if getattr(task, "needs_data", False):
                task_data_dir = self._task_data_dir(base_data_dir, task)
                task_data_dir.mkdir(parents=True, exist_ok=True)

                if data_info is not None:
                    _safe_write_json(task_eval_dir / "data_info.json", data_info)

                logger.debug(f"Data info for task {task.id}: {data_info}")


                if not getattr(task, "reuse_existing", True):
                    # Force a clean re-download for this task configuration
                    try:
                        shutil.rmtree(task_data_dir)
                    except FileNotFoundError:
                        pass
                    os.makedirs(task_data_dir, exist_ok=True)

                await updater.update_status(
                    TaskState.working,
                    new_agent_text_message(f"[{task.id}] Ensuring data in {task_data_dir} ..."),
                )
                logger.info(f"[{task.id}] Ensuring data in {task_data_dir} ...")

                try:
                    # NOTE: workers not in TaskSpec -> pick a sane default or read env
                    workers = int(os.getenv("HEPEX_DOWNLOAD_WORKERS", "6"))
                    data_info = ensure_atlas_open_data_downloaded(
                        skim=task.skim,
                        release=task.release,
                        dataset=task.dataset,
                        protocol=task.protocol,
                        output_dir=task_data_dir,
                        max_files=task.max_files or 0,
                        workers=workers,
                        verbose=True,
                    )
                except Exception as e:
                    task_report = {
                        "task_id": task.id,
                        "type": task.type,
                        "status": "error",
                        "error": f"Data download failed: {type(e).__name__}: {e}",
                        "final": {"total_score": 0.0, "max_score": 1.0, "normalized_score": 0.0},
                    }
                    overall["tasks"].append(task_report)

                    await updater.add_artifact(
                        parts=[
                            Part(root=TextPart(text=f"[{task.id}] ERROR: data download failed.")),
                            Part(root=DataPart(data=task_report)),
                        ],
                        name=f"Result-{task.id}",
                    )
                    continue

                n_ok = data_info.get("n_ok", data_info.get("n_files", 0))
                await updater.update_status(
                    TaskState.working,
                    new_agent_text_message(f"[{task.id}] Data ready: {n_ok} files."),
                )

            # 3b) Get submission trace
            try:
                submission_trace = await self._get_submission_trace(task, request, data_info)
            except Exception as e:
                submission_trace = {
                    "task_id": task.id,
                    "status": "error",
                    "error": f"Failed to get submission trace: {type(e).__name__}: {e}",
                }
            
            _safe_write_json(task_eval_dir / "submission_trace.json", submission_trace)


            # persist judge input snapshot (what engine sees)
            # Sensitive eval fields are stripped so this file is safe to write
            # in a public-facing run directory.
            _SENSITIVE_TASK_FIELDS = {
                "rubric_path", "eval_ref_path", "judge_prompt_path", "white_prompt_path"
            }
            judge_input = {
                "task_spec": {
                    k: v for k, v in task.model_dump().items()
                    if k not in _SENSITIVE_TASK_FIELDS
                },
                "data_info": data_info,
                "submission_trace": submission_trace,
            }
            _safe_write_json(task_eval_dir / "judge_input.json", judge_input)

            # 3c) Evaluate
            try:

                bundle = load_spec_bundle(task)  # {rubric, eval_ref, judge_prompt, ...}
                eval_ref = bundle.get("eval_ref", {}) or {}

                if bundle["rubric"]:
                    # --- V1 path: private rubric available → full scoring ---
                    spec = {
                        "task": task.model_dump(),
                        "rubric": bundle["rubric"],
                        "eval_ref": eval_ref,
                        "judge_prompt": bundle.get("judge_prompt"),
                    }
                    gemini = self.gemini_judge if (spec["rubric"].get("llm_checks") and spec.get("judge_prompt")) else None
                    report = evaluate_task(
                        spec=spec,
                        trace=submission_trace,
                        gemini=gemini,
                    )
                else:
                    # --- V2 path: no rubric → public-safe contract validation ---
                    from engine.contract_validator import validate_contract
                    report = validate_contract(task, submission_trace)

            except Exception as e:
                err_text = f"{type(e).__name__}: {e}"
                _safe_write_text(task_eval_dir / "engine_error.txt", err_text)

                report = {
                    "task_id": task.id,
                    "type": task.type,
                    "status": "error",
                    "error": f"Engine failed: {err_text}",
                    "final": {"total_score": 0.0, "max_score": 1.0, "normalized_score": 0.0},
                }

            # Ensure task_id and type are always in the report
            report["task_id"] = task.id
            report["type"] = task.type

            # 3d) Normalize and accumulate
            final = report.setdefault("final", {})
            total_score = float(final.get("total_score", 0.0))
            max_score = float(final.get("max_score", 100.0))
            denom = max(1e-9, max_score)
            normalized = total_score / denom

            final["total_score"] = total_score
            final["max_score"] = max_score
            final["normalized_score"] = normalized

            overall["score_total"] += normalized
            overall["tasks"].append(report)

            _safe_write_json(task_eval_dir / "judge_output.json", report)

            # update meta with score
            meta.update({
                "score_total": total_score,
                "score_max": max_score,
                "normalized_score": normalized,
                "finished_at": _utc_now_iso(),
                "status": report.get("status", "ok"),
            })
            _safe_write_json(task_eval_dir / "meta.json", meta)

            summary = f"[{task.id}] {task.type}: score={total_score:.2f}/{max_score:.2f} (norm={normalized:.3f})"
            logger.info(summary)
            await updater.add_artifact(
                parts=[Part(root=TextPart(text=summary)), Part(root=DataPart(data=report))],
                name=f"Result-{task.id}",
            )

        # 4) Summary
        done_text = (
            f"Done. Normalized score: {overall['score_total']:.3f}/{overall['score_max']:.3f}\n"
            f"run_id={overall['run_id']}\n"
            f"run_dir={overall['run_dir']}"
        )

        await updater.add_artifact(
            parts=[Part(root=TextPart(text=done_text)), Part(root=DataPart(data=overall))],
            name="Summary",
        )

        # 5) Complete (if supported)
        try:
            await updater.complete(new_agent_text_message(done_text))
        except Exception:
            await updater.update_status(TaskState.working, new_agent_text_message(done_text))
