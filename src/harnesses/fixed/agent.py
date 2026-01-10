from __future__ import annotations

from typing import Any
from pathlib import Path
import yaml

from pydantic import BaseModel, HttpUrl, ValidationError
from a2a.server.tasks import TaskUpdater
from a2a.types import Message, TaskState, Part, TextPart, DataPart
from a2a.utils import get_message_text, new_agent_text_message

from messenger import Messenger
from .scorer import score_fixed_accuracy

TASK_DIR = Path(__file__).resolve().parents[2] / "tasks"

class EvalRequest(BaseModel):
    """Request format sent by the AgentBeats platform to green agents."""
    participants: dict[str, HttpUrl]  # role -> agent URL
    config: dict[str, Any]


class Agent:
    # v0 fixed harness: needs a white agent + a test yaml path
    required_roles: list[str] = ["white_agent"]
    required_config_keys: list[str] = ["test_file"]

    def __init__(self):
        self.messenger = Messenger()

    def validate_request(self, request: EvalRequest) -> tuple[bool, str]:
        missing_roles = set(self.required_roles) - set(request.participants.keys())
        if missing_roles:
            return False, f"Missing roles: {missing_roles}"

        missing_config_keys = set(self.required_config_keys) - set(request.config.keys())
        if missing_config_keys:
            return False, f"Missing config keys: {missing_config_keys}"

        test_file = request.config.get("test_file")
        if not isinstance(test_file, str) or not test_file.strip():
            return False, "config.test_file must be a non-empty string"

        return True, "ok"

    def _load_yaml(self, rel_path: str) -> dict[str, Any]:
        path = (TASK_DIR / rel_path).resolve()
        # prevent path traversal
        if not str(path).startswith(str(TASK_DIR.resolve())):
            raise ValueError("Invalid test_file path (outside TASK_DIR)")
        if not path.exists():
            raise FileNotFoundError(f"Test file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _render_prompt_minimal(self, template: str, params: dict[str, Any]) -> str:
        # Minimal v0 renderer: replaces {{ key }} with str(value)
        out = template
        for k, v in params.items():
            out = out.replace("{{ " + k + " }}", str(v))
            out = out.replace("{{" + k + "}}", str(v))
        return out

    async def run(self, message: Message, updater: TaskUpdater) -> None:
        input_text = get_message_text(message)

        # --- parse platform request ---
        try:
            request: EvalRequest = EvalRequest.model_validate_json(input_text)
            ok, msg = self.validate_request(request)
            if not ok:
                await updater.reject(new_agent_text_message(msg))
                return
        except ValidationError as e:
            await updater.reject(new_agent_text_message(f"Invalid request: {e}"))
            return

        test_file: str = request.config["test_file"]
        white_url = request.participants["white_agent"]

        # --- load test spec ---
        try:
            spec = self._load_yaml(test_file)
        except Exception as e:
            await updater.reject(new_agent_text_message(f"Failed to load test yaml: {e}"))
            return

        task = spec.get("task", {}) or {}
        task_id = task.get("id", "unknown")
        task_name = task.get("name", "")

        white_cfg = spec.get("white_agent", {}) or {}
        prompt_template = white_cfg.get("prompt_template")
        if not isinstance(prompt_template, str) or not prompt_template.strip():
            await updater.reject(new_agent_text_message("white_agent.prompt_template must be a non-empty string"))
            return

        # v0: derive p_values from rubric.ground_truth (single source of truth)
        ground_truth = (spec.get("rubric", {}) or {}).get("ground_truth", []) or []
        try:
            p_values = [float(row["p"]) for row in ground_truth]
        except Exception:
            await updater.reject(new_agent_text_message("rubric.ground_truth must contain entries with key 'p'"))
            return

        prompt = self._render_prompt_minimal(prompt_template, {"p_values": p_values})

        await updater.update_status(
            TaskState.working,
            new_agent_text_message(f"Running fixed harness test: {test_file} ({task_id})"),
        )

        # --- call white agent ---
        try:
            white_reply_msg = await self.messenger.talk_to_agent(
                new_agent_text_message(prompt),
                str(white_url),
            )
        except Exception as e:
            await updater.failed(new_agent_text_message(f"White agent call failed: {e}"))
            return

        white_text = get_message_text(white_reply_msg)

        # --- score ---
        try:
            score_res = score_fixed_accuracy(spec=spec, white_text=white_text)
        except Exception as e:
            await updater.failed(new_agent_text_message(f"Scoring failed: {e}"))
            return

        result = {
            "harness": "fixed",
            "task_id": task_id,
            "task_name": task_name,
            "test_file": test_file,
            "score": score_res.score,
            "correct": score_res.correct,
            "total": score_res.total,
            "parse_ok": score_res.parse_ok,
            "per_item": score_res.per_item,
            "white_raw_response": score_res.raw_response,
        }

        await updater.add_artifact(
            parts=[
                Part(root=TextPart(text=f"Score: {score_res.score:.3f} ({score_res.correct}/{score_res.total}) — {task_name}")),
                Part(root=DataPart(data=result)),
            ],
            name="Result",
        )
