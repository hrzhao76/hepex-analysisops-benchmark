import base64
import gzip
import json

import yaml

from engine.secret_store import SecretStore


def test_secret_store_reads_gzipped_private_rubric():
    rubric = {"version": 1, "checks": {"execution": [{"id": "required_trace"}]}}
    rubric_yaml = yaml.safe_dump(rubric, sort_keys=False)
    payload = {
        "schema_version": 1,
        "tasks": {
            "task_a": {
                "private_rubric_yaml_gz_b64": base64.b64encode(
                    gzip.compress(rubric_yaml.encode("utf-8"), mtime=0)
                ).decode("utf-8")
            }
        },
        "judge_env": {},
    }

    loaded = SecretStore(json.dumps(payload)).get_task_private_rubric("task_a")

    assert loaded["checks"]["execution"][0]["id"] == "required_trace"


def test_secret_store_still_reads_legacy_plain_private_rubric():
    rubric = {"version": 1, "checks": {"execution": [{"id": "required_trace"}]}}
    rubric_yaml = yaml.safe_dump(rubric, sort_keys=False)
    payload = {
        "schema_version": 1,
        "tasks": {
            "task_a": {
                "private_rubric_yaml_b64": base64.b64encode(rubric_yaml.encode("utf-8")).decode("utf-8")
            }
        },
        "judge_env": {},
    }

    loaded = SecretStore(json.dumps(payload)).get_task_private_rubric("task_a")

    assert loaded["checks"]["execution"][0]["id"] == "required_trace"
