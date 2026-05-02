#!/usr/bin/env python3
"""Build GREEN_SECRETS_JSON from a private rubric and write it to .env files."""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from engine.package_loader import load_submission_contract
from engine.secret_store import SecretStore
from tasks.task_spec import load_task_spec


DEFAULT_TASK_DIR = REPO_ROOT / "tasks_public" / "t002_hyy_v5_l1"
DEFAULT_PRIVATE_RUBRIC = (
    REPO_ROOT.parent
    / "hepex-analysisops-dev"
    / "benchmark"
    / "tasks"
    / "Hyy_v5"
    / "l1_package_finetune"
    / "private_rubric.yaml"
)
DEFAULT_ENV_FILES = [
    REPO_ROOT / ".env",
    REPO_ROOT.parent / "hepex-analysisops-leaderboard" / ".env",
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


def build_green_secrets_json(
    *,
    task_dir: Path,
    private_rubric_path: Path,
    judge_env: Iterable[tuple[str, str]],
) -> tuple[str, str, str]:
    task = load_task_spec(task_dir)
    contract = load_submission_contract(task)
    contract_hash = SecretStore("").contract_hash(contract)

    rubric_text = private_rubric_path.read_text(encoding="utf-8")
    rubric_obj = yaml.safe_load(rubric_text) or {}
    if not isinstance(rubric_obj, dict):
        raise SystemExit(f"Private rubric must be a YAML mapping: {private_rubric_path}")

    rubric_b64 = base64.b64encode(rubric_text.encode("utf-8")).decode("utf-8")
    payload = {
        "schema_version": 1,
        "tasks": {
            task.id: {
                "public_contract_sha256": contract_hash,
                "private_rubric_yaml_b64": rubric_b64,
            }
        },
        "judge_env": dict(judge_env),
    }
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False), task.id, contract_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", type=Path, default=DEFAULT_TASK_DIR)
    parser.add_argument("--private-rubric", type=Path, default=DEFAULT_PRIVATE_RUBRIC)
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

    secret_json, task_id, contract_hash = build_green_secrets_json(
        task_dir=args.task_dir,
        private_rubric_path=args.private_rubric,
        judge_env=args.judge_env,
    )

    env_files = args.env_file or DEFAULT_ENV_FILES
    if not args.dry_run:
        for env_file in env_files:
            update_env_file(env_file, "GREEN_SECRETS_JSON", secret_json)

    print(f"Built GREEN_SECRETS_JSON for task={task_id} contract_sha256={contract_hash}")
    if args.dry_run:
        print("Dry run: no .env files were changed.")
    else:
        for env_file in env_files:
            print(f"Updated {env_file}")
    if args.stdout:
        print(secret_json)


if __name__ == "__main__":
    main()
