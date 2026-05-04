from __future__ import annotations

import base64
import copy
import gzip
import hashlib
import json
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

import yaml


class SecretStore:
    ENV_NAME = "GREEN_SECRETS_JSON"

    def __init__(self, raw_json: Optional[str] = None):
        self._raw_json = raw_json if raw_json is not None else os.getenv(self.ENV_NAME, "")
        self._data = self._parse(self._raw_json)

    @staticmethod
    def _parse(raw_json: str) -> Dict[str, Any]:
        if not raw_json:
            return {}
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def contract_hash(self, contract: Dict[str, Any]) -> str:
        payload = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get_task_private_rubric(self, task_id: Optional[str], *, public_contract_hash: Optional[str] = None) -> Dict[str, Any]:
        if not task_id:
            return {}
        task_entry = ((self._data.get("tasks") or {}).get(task_id) or {})
        if not isinstance(task_entry, dict):
            return {}

        expected_hash = task_entry.get("public_contract_sha256")
        if expected_hash and public_contract_hash and expected_hash != public_contract_hash:
            return {}

        try:
            decoded = self._decode_private_rubric_yaml(task_entry)
        except Exception:
            return {}
        if not decoded:
            return {}
        obj = yaml.safe_load(decoded) or {}
        return obj if isinstance(obj, dict) else {}

    @staticmethod
    def _decode_private_rubric_yaml(task_entry: Dict[str, Any]) -> str:
        raw_gz_b64 = task_entry.get("private_rubric_yaml_gz_b64")
        if isinstance(raw_gz_b64, str) and raw_gz_b64.strip():
            compressed = base64.b64decode(raw_gz_b64.encode("utf-8"))
            return gzip.decompress(compressed).decode("utf-8")

        raw_b64 = task_entry.get("private_rubric_yaml_b64")
        if isinstance(raw_b64, str) and raw_b64.strip():
            return base64.b64decode(raw_b64.encode("utf-8")).decode("utf-8")

        return ""

    def get_judge_env(self) -> Dict[str, str]:
        judge_env = self._data.get("judge_env") or {}
        if not isinstance(judge_env, dict):
            return {}
        return {str(k): str(v) for k, v in judge_env.items()}


@contextmanager
def patched_env(env_updates: Dict[str, str]) -> Iterator[None]:
    snapshot = copy.deepcopy(os.environ)
    try:
        os.environ.update(env_updates)
        yield
    finally:
        os.environ.clear()
        os.environ.update(snapshot)
