#!/usr/bin/env python3
"""Build GREEN_SECRETS_JSON from private rubrics and write it to .env files.

By default this exports the Hyy v5 L1, L2, and L3 private rubrics together. The
rubric source files are cached under private_rubrics/, which is ignored by git.
Pass --task-dir/--private-rubric to preserve the older single-task behavior.
"""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from engine.package_loader import load_submission_contract
from engine.schema_validator import require_valid, validate_private_rubric_document
from engine.secret_store import SecretStore
from tasks.task_spec import load_task_spec


PRIVATE_RUBRIC_CACHE_DIR = REPO_ROOT / "private_rubrics"
DEFAULT_L1_TASK_DIR = REPO_ROOT / "tasks_public" / "t002_hyy_v5_l1"
DEFAULT_L2_TASK_DIR = REPO_ROOT / "tasks_public" / "t003_hyy_v5_l2"
DEFAULT_L3_TASK_DIR = REPO_ROOT / "tasks_public" / "t004_hyy_v5_l3"
DEFAULT_L1_PRIVATE_RUBRIC = PRIVATE_RUBRIC_CACHE_DIR / "hyy_v5_l1_private_rubric.yaml"
DEFAULT_L2_PRIVATE_RUBRIC = PRIVATE_RUBRIC_CACHE_DIR / "hyy_v5_l2_private_rubric.yaml"
DEFAULT_L3_PRIVATE_RUBRIC = PRIVATE_RUBRIC_CACHE_DIR / "hyy_v5_l3_private_rubric.yaml"
DEV_L1_PRIVATE_RUBRIC = (
    REPO_ROOT.parent
    / "hepex-analysisops-dev"
    / "benchmark"
    / "tasks"
    / "Hyy_v5"
    / "l1_package_finetune"
    / "private_rubric.yaml"
)
DEV_L2_PRIVATE_RUBRIC = (
    REPO_ROOT.parent
    / "hepex-analysisops-dev"
    / "benchmark"
    / "outputs"
    / "auto_full_v2_20260501T200248"
    / "l2_package"
    / "private_rubric.yaml"
)
DEV_L3_PRIVATE_RUBRIC = (
    REPO_ROOT.parent
    / "hepex-analysisops-dev"
    / "benchmark"
    / "outputs"
    / "auto_full_v2_20260501T200248"
    / "l3_package"
    / "private_rubric.yaml"
)
DEFAULT_ENV_FILES = [
    REPO_ROOT / ".env",
    REPO_ROOT.parent / "hepex-analysisops-leaderboard" / ".env",
]


@dataclass(frozen=True)
class TaskSecretSource:
    task_dir: Path
    private_rubric_path: Path
    fallback_private_rubric_path: Optional[Path] = None


DEFAULT_TASK_SOURCES = [
    TaskSecretSource(
        task_dir=DEFAULT_L1_TASK_DIR,
        private_rubric_path=DEFAULT_L1_PRIVATE_RUBRIC,
        fallback_private_rubric_path=DEV_L1_PRIVATE_RUBRIC,
    ),
    TaskSecretSource(
        task_dir=DEFAULT_L2_TASK_DIR,
        private_rubric_path=DEFAULT_L2_PRIVATE_RUBRIC,
        fallback_private_rubric_path=DEV_L2_PRIVATE_RUBRIC,
    ),
    TaskSecretSource(
        task_dir=DEFAULT_L3_TASK_DIR,
        private_rubric_path=DEFAULT_L3_PRIVATE_RUBRIC,
        fallback_private_rubric_path=DEV_L3_PRIVATE_RUBRIC,
    ),
]


def parse_env_pair(raw: str) -> tuple[str, str]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(f"Expected KEY=VALUE, got {raw!r}")
    key, value = raw.split("=", 1)
    key = key.strip()
    if not key:
        raise argparse.ArgumentTypeError(f"Empty env key in {raw!r}")
    return key, value


def quote_env_value(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def update_env_file(path: Path, key: str, value: str) -> None:
    assignment = f"{key}={quote_env_value(value)}"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    replaced = False
    updated: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and stripped.split("=", 1)[0] == key:
            updated.append(assignment)
            replaced = True
        else:
            updated.append(line)

    if not replaced:
        if updated and updated[-1].strip():
            updated.append("")
        updated.append(assignment)

    path.write_text("\n".join(updated) + "\n", encoding="utf-8")


def _copy_if_needed(src: Path, dst: Path) -> None:
    if dst.exists() and dst.read_bytes() == src.read_bytes():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    print(f"Cached private rubric source: {dst}")


def resolve_private_rubric_path(source: TaskSecretSource) -> Path:
    if source.fallback_private_rubric_path and source.fallback_private_rubric_path.exists():
        _copy_if_needed(source.fallback_private_rubric_path, source.private_rubric_path)

    if source.private_rubric_path.exists():
        return source.private_rubric_path

    fallback = source.fallback_private_rubric_path
    fallback_text = f" fallback={fallback}" if fallback else ""
    raise SystemExit(f"Private rubric file not found: {source.private_rubric_path}.{fallback_text}")


def build_task_secret_entry(source: TaskSecretSource) -> tuple[str, dict[str, str], str]:
    task = load_task_spec(source.task_dir)
    contract = load_submission_contract(task)
    contract_hash = SecretStore("").contract_hash(contract)
    private_rubric_path = resolve_private_rubric_path(source)

    rubric_text = private_rubric_path.read_text(encoding="utf-8")
    rubric_obj = yaml.safe_load(rubric_text) or {}
    if not isinstance(rubric_obj, dict):
        raise SystemExit(f"Private rubric must be a YAML mapping: {private_rubric_path}")
    require_valid(validate_private_rubric_document(rubric_obj), label=f"private rubric {private_rubric_path}")

    rubric_b64 = base64.b64encode(rubric_text.encode("utf-8")).decode("utf-8")
    entry = {
        "public_contract_sha256": contract_hash,
        "private_rubric_yaml_b64": rubric_b64,
    }
    return task.id, entry, contract_hash


def build_green_secrets_json(
    *,
    sources: Iterable[TaskSecretSource],
    judge_env: Iterable[tuple[str, str]],
) -> tuple[str, list[tuple[str, str]]]:
    task_entries: dict[str, dict[str, str]] = {}
    summaries: list[tuple[str, str]] = []
    for source in sources:
        task_id, entry, contract_hash = build_task_secret_entry(source)
        if task_id in task_entries:
            raise SystemExit(f"Duplicate task id in secret export: {task_id}")
        task_entries[task_id] = entry
        summaries.append((task_id, contract_hash))

    payload = {
        "schema_version": 1,
        "tasks": task_entries,
        "judge_env": dict(judge_env),
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False), summaries


def requested_sources(args: argparse.Namespace) -> list[TaskSecretSource]:
    if args.task_dir is None and args.private_rubric is None:
        return DEFAULT_TASK_SOURCES
    task_dir = (args.task_dir or DEFAULT_L1_TASK_DIR).resolve()
    if args.private_rubric:
        private_rubric_path = args.private_rubric.resolve()
        fallback_private_rubric_path = None
    elif task_dir == DEFAULT_L2_TASK_DIR.resolve() or task_dir.name == DEFAULT_L2_TASK_DIR.name:
        private_rubric_path = DEFAULT_L2_PRIVATE_RUBRIC.resolve()
        fallback_private_rubric_path = DEV_L2_PRIVATE_RUBRIC
    elif task_dir == DEFAULT_L3_TASK_DIR.resolve() or task_dir.name == DEFAULT_L3_TASK_DIR.name:
        private_rubric_path = DEFAULT_L3_PRIVATE_RUBRIC.resolve()
        fallback_private_rubric_path = DEV_L3_PRIVATE_RUBRIC
    else:
        private_rubric_path = DEFAULT_L1_PRIVATE_RUBRIC.resolve()
        fallback_private_rubric_path = DEV_L1_PRIVATE_RUBRIC
    return [
        TaskSecretSource(
            task_dir=task_dir,
            private_rubric_path=private_rubric_path,
            fallback_private_rubric_path=fallback_private_rubric_path,
        )
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--task-dir",
        type=Path,
        default=None,
        help="Export a single task from this task directory. Omit to export default L1+L2 tasks.",
    )
    parser.add_argument(
        "--private-rubric",
        type=Path,
        default=None,
        help="Private rubric YAML/JSON for --task-dir. Omit to use the default cached Hyy v5 L1 rubric.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        action="append",
        help="Env file to update. Defaults to benchmark .env and leaderboard .env.",
    )
    parser.add_argument(
        "--judge-env",
        type=parse_env_pair,
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Optional judge env entry to embed in GREEN_SECRETS_JSON.",
    )
    parser.add_argument("--stdout", action="store_true", help="Print the generated value to stdout.")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without writing .env files.")
    args = parser.parse_args()

    secret_json, summaries = build_green_secrets_json(
        sources=requested_sources(args),
        judge_env=args.judge_env,
    )

    env_files = args.env_file or DEFAULT_ENV_FILES
    if not args.dry_run:
        for env_file in env_files:
            update_env_file(env_file, "GREEN_SECRETS_JSON", secret_json)

    task_list = ", ".join(f"{task_id}:{contract_hash}" for task_id, contract_hash in summaries)
    print(f"Built GREEN_SECRETS_JSON for {len(summaries)} task(s): {task_list}")
    if args.dry_run:
        print("Dry run: no .env files were changed.")
    else:
        for env_file in env_files:
            print(f"Updated {env_file}")
    if args.stdout:
        print(secret_json)


if __name__ == "__main__":
    main()
