from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from .contract_validator import validate_submission_dir
from .rubric_scorer import rubric_unavailable_report, score_submission
from .llm_judge import BaseJudge, configured_judge_metadata, get_judge, judge_runtime_metadata
from .package_loader import load_private_rubric
from .secret_store import SecretStore, patched_env


SUPPORTED_EVALUATION_MODES = {
    "directory_contract_and_private_l1",
    "directory_contract_and_private_rubric_v1",
}


class EvaluationEngine:
    def __init__(
        self,
        *,
        fallback_judge: Optional[BaseJudge] = None,
        judge_factory: Callable[[], BaseJudge] = get_judge,
        secret_store_factory: Callable[[], SecretStore] = SecretStore,
    ) -> None:
        self.fallback_judge = fallback_judge
        self.judge_factory = judge_factory
        self.secret_store_factory = secret_store_factory

    def _build_secret_backed_judge(self, secret_store: SecretStore) -> Optional[BaseJudge]:
        judge_env = secret_store.get_judge_env()
        if not judge_env:
            return self.fallback_judge
        with patched_env(judge_env):
            try:
                return self.judge_factory()
            except RuntimeError:
                return self.fallback_judge

    def judge_metadata(self, secret_store: Optional[SecretStore] = None, judge: Optional[BaseJudge] = None) -> dict[str, Any]:
        secret_store = secret_store or self.secret_store_factory()
        configured = configured_judge_metadata(secret_store.get_judge_env())
        return judge_runtime_metadata(judge if judge is not None else self.fallback_judge, configured=configured)

    def evaluate_submission(self, task: Any, submission_dir: Path) -> dict[str, Any]:
        if getattr(task, "evaluation_mode", None) not in SUPPORTED_EVALUATION_MODES:
            raise RuntimeError(
                f"Unsupported evaluation_mode for task {getattr(task, 'id', 'unknown')}: "
                f"{getattr(task, 'evaluation_mode', None)}"
            )

        contract_report = validate_submission_dir(task, submission_dir)
        if contract_report.get("status") != "ok":
            contract_report["llm"] = {"judge": self.judge_metadata()}
            return contract_report

        secret_store = self.secret_store_factory()
        judge = self._build_secret_backed_judge(secret_store)
        private_rubric = load_private_rubric(task, secret_store)
        if private_rubric:
            report = score_submission(
                task,
                submission_dir,
                private_rubric,
                contract_report,
                judge=judge,
            )
            report["llm"] = {"judge": self.judge_metadata(secret_store, judge)}
            return report

        report = rubric_unavailable_report(
            task,
            contract_report,
            reason=(
                "Task requires private-rubric scoring, but no matching private rubric was "
                "available from GREEN_SECRETS_JSON."
            ),
        )
        report["llm"] = {"judge": self.judge_metadata(secret_store, judge)}
        return report
