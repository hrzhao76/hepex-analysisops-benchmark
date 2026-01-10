from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, HttpUrl, ValidationError
from a2a.server.tasks import TaskUpdater
from a2a.types import Message, TaskState, Part, TextPart, DataPart
from a2a.utils import get_message_text, new_agent_text_message

from messenger import Messenger

from tasks.task_spec import GreenConfig, TaskSpec
from utils.atlas_download import ensure_data_downloaded

from engine.runner import run_engine_for_task
from utils.mock_traces import mock_trace_zpeak_fit, mock_trace_hyy


class EvalRequest(BaseModel):
    """Request format sent by the AgentBeats platform to green agents."""
    participants: dict[str, HttpUrl]  # role -> agent URL
    config: dict[str, Any]


class Agent:
    # For mock mode, you don't need white_agent. When you implement call_white, set to ["white_agent"].
    required_roles: list[str] = []
    required_config_keys: list[str] = ["tasks", "data_dir", "release"]

    def __init__(self):
        self.messenger = Messenger()

    def validate_request(self, request: EvalRequest) -> tuple[bool, str]:
        missing_roles = set(self.required_roles) - set(request.participants.keys())
        if missing_roles:
            return False, f"Missing roles: {missing_roles}"

        missing_config_keys = set(self.required_config_keys) - set(request.config.keys())
        if missing_config_keys:
            return False, f"Missing config keys: {missing_config_keys}"

        return True, "ok"

    async def _get_submission_trace(
        self,
        task: TaskSpec,
        request: EvalRequest,
        data_info: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """
        Produce a submission_trace dict for the task.
        - mock: return canned traces
        - call_white: TODO (future)
        """
        # --- mock mode ---
        if getattr(task, "mode", "mock") == "mock":
            if task.type == "zpeak_fit":
                return mock_trace_zpeak_fit(task.id)
            if task.type == "hyy_analysis":
                return mock_trace_hyy(task.id)
            return {"task_id": task.id, "status": "error", "error": f"Unknown task type: {task.type}"}

        # --- future: call white agent ---
        # When enabled, you should require_roles=["white_agent"] and pass payload including:
        # - data_info["local_paths"] (or data_dir)
        # - task.workflow_spec_path / rubric_path (or the loaded content)
        # - expected output trace schema
        #
        # white_url = str(request.participants["white_agent"])
        # payload = {
        #     "task_id": task.id,
        #     "type": task.type,
        #     "data": {"local_paths": (data_info or {}).get("local_paths", [])},
        #     "workflow_spec_path": task.workflow_spec_path,
        #     "rubric_path": task.rubric_path,
        # }
        # white_reply = await self.messenger.talk_to_agent(
        #     new_agent_text_message(json.dumps(payload)), white_url
        # )
        # return json.loads(get_message_text(white_reply))

        return {
            "task_id": task.id,
            "status": "error",
            "error": "call_white not implemented yet",
        }

    async def run(self, message: Message, updater: TaskUpdater) -> None:
        input_text = get_message_text(message)

        # 1) Parse platform request
        try:
            request: EvalRequest = EvalRequest.model_validate_json(input_text)
            ok, msg = self.validate_request(request)
            if not ok:
                await updater.reject(new_agent_text_message(msg))
                return
        except ValidationError as e:
            await updater.reject(new_agent_text_message(f"Invalid request: {e}"))
            return

        # 2) Parse green config
        try:
            cfg = GreenConfig.model_validate(request.config)
        except ValidationError as e:
            await updater.reject(new_agent_text_message(f"Invalid config: {e}"))
            return

        await updater.update_status(TaskState.working, new_agent_text_message("Starting tasks..."))

        overall: dict[str, Any] = {
            "release": cfg.release,
            "data_dir": cfg.data_dir,
            "tasks": [],
            "score_total": 0.0,
            "score_max": float(len(cfg.tasks)),
        }

        # 3) Run tasks sequentially
        for idx, task in enumerate(cfg.tasks, start=1):
            await updater.update_status(
                TaskState.working,
                new_agent_text_message(f"Task {idx}/{len(cfg.tasks)}: {task.type} ({task.id})"),
            )

            # 3a) Download data (optional)
            data_info: Optional[dict[str, Any]] = None
            if getattr(task, "needs_data", False):
                await updater.update_status(
                    TaskState.working,
                    new_agent_text_message(f"[{task.id}] Downloading/caching data via atlasopenmagic..."),
                )
                try:
                    data_info = ensure_data_downloaded(cfg, task)  # uses cfg.release, task.dataset/skim/etc.
                except Exception as e:
                    task_report = {
                        "task_id": task.id,
                        "type": task.type,
                        "status": "error",
                        "error": f"Data download failed: {type(e).__name__}: {e}",
                        "final": {"total_score": 0.0, "max_score": 100.0},
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

                await updater.update_status(
                    TaskState.working,
                    new_agent_text_message(f"[{task.id}] Data ready: {data_info.get('n_files', 0)} files cached."),
                )

            # 3b) Get submission trace (mock now; later from white agent)
            submission_trace = await self._get_submission_trace(task, request, data_info)

            # 3c) Run engine evaluation
            report = run_engine_for_task(
                task_spec=task,
                data_info=data_info,
                submission_trace=submission_trace,
            )

            # update totals
            final_score = float(report.get("final", {}).get("total_score", 0.0))
            overall["score_total"] += final_score / max(1.0, float(report.get("final", {}).get("max_score", 100.0)))

            overall["tasks"].append(report)

            # human summary
            max_score = report.get("final", {}).get("max_score", 100.0)
            summary = f"[{task.id}] {task.type}: score={final_score:.2f}/{max_score}"

            await updater.add_artifact(
                parts=[
                    Part(root=TextPart(text=summary)),
                    Part(root=DataPart(data=report)),
                ],
                name=f"Result-{task.id}",
            )

        # 4) Final summary artifact
        await updater.update_status(TaskState.working, new_agent_text_message("All tasks finished."))
        await updater.add_artifact(
            parts=[
                Part(root=TextPart(text=f"Done. Normalized score: {overall['score_total']:.3f}/{overall['score_max']:.3f}")),
                Part(root=DataPart(data=overall)),
            ],
            name="Summary",
        )
