from __future__ import annotations

import json
import logging
from typing import Any

from a2a.server.tasks import TaskUpdater
from a2a.types import DataPart, Message, Part, TaskState, TextPart
from a2a.utils import get_message_text, new_agent_text_message
from dotenv import find_dotenv, load_dotenv
from pydantic import ValidationError

from engine.benchmark_engine import BenchmarkEngine
from engine.evaluation import EvaluationEngine
from engine.llm_judge import get_judge
from engine.run_models import EvalRequest
from messenger import Messenger


logger = logging.getLogger(__name__)


class AgentSolverTransport:
    def __init__(self, *, messenger: Messenger, request: EvalRequest) -> None:
        self.messenger = messenger
        self.request = request

    @staticmethod
    def _resolve_purple_agent_url(request: EvalRequest) -> str:
        purple_url = request.participants.get("purple_agent")
        if purple_url is not None:
            return str(purple_url)
        if len(request.participants) == 1:
            return str(next(iter(request.participants.values())))
        raise KeyError("Missing participant role: expected 'purple_agent'.")

    def _solver_request_timeout_seconds(self) -> int | None:
        raw = self.request.config.get("solver_request_timeout_seconds")
        if raw is None:
            return None
        return int(raw)

    async def request_submission_bundle(self, payload: dict[str, Any]) -> str:
        timeout = self._solver_request_timeout_seconds()
        kwargs = {"timeout": timeout} if timeout is not None else {}
        return await self.messenger.talk_to_agent(
            message=json.dumps(payload, indent=2),
            url=self._resolve_purple_agent_url(self.request),
            new_conversation=True,
            **kwargs,
        )


class A2ARunObserver:
    def __init__(self, updater: TaskUpdater) -> None:
        self.updater = updater

    async def status(self, text: str) -> None:
        await self.updater.update_status(TaskState.working, new_agent_text_message(text))

    async def task_result(self, name: str, summary: str, report: dict[str, Any]) -> None:
        await self.updater.add_artifact(
            parts=[Part(root=TextPart(text=summary)), Part(root=DataPart(data=report))],
            name=name,
        )

    async def summary(self, text: str, overall: dict[str, Any]) -> None:
        await self.updater.add_artifact(
            parts=[Part(root=TextPart(text=text))],
            name="Summary",
        )


class Agent:
    required_roles: list[str] = []

    def __init__(self):
        load_dotenv(find_dotenv())
        self.messenger = Messenger()
        try:
            self.llm_judge = get_judge()
        except RuntimeError as e:
            logger.warning(f"Judge initialization failed, evaluation requiring LLMs will fail: {e}")
            self.llm_judge = None
        self.benchmark_engine = BenchmarkEngine(
            evaluation_engine=EvaluationEngine(fallback_judge=self.llm_judge)
        )

    def validate_request(self, request: EvalRequest) -> tuple[bool, str]:
        participant_keys = set(request.participants.keys())
        missing_roles = set(self.required_roles) - participant_keys
        if missing_roles:
            return False, f"Missing roles: {sorted(missing_roles)}"
        return True, "ok"

    async def run(self, message: Message, updater: TaskUpdater) -> None:
        input_text = get_message_text(message)

        try:
            request = EvalRequest.model_validate_json(input_text)
            ok, msg = self.validate_request(request)
            logger.info(f"Received request: {request}")
            await updater.update_status(TaskState.working, new_agent_text_message(f"Received request: {request}"))
            if not ok:
                await updater.reject(new_agent_text_message(msg))
                return
        except ValidationError as e:
            await updater.reject(new_agent_text_message(f"Invalid request: {e}"))
            return

        transport = AgentSolverTransport(messenger=self.messenger, request=request)
        observer = A2ARunObserver(updater)

        try:
            result = await self.benchmark_engine.run(request, transport, observer)
        except ValidationError as e:
            await updater.reject(new_agent_text_message(f"Invalid config: {e}"))
            return

        try:
            await updater.complete(new_agent_text_message(result.done_text))
        except Exception:
            await updater.update_status(TaskState.working, new_agent_text_message(result.done_text))
