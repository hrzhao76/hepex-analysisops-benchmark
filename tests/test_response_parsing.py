from __future__ import annotations

from types import SimpleNamespace

from engine.benchmark_engine import BenchmarkEngine
from messenger import _extract_task_payload_text


def _text_part(text: str):
    return SimpleNamespace(root=SimpleNamespace(text=text))


def test_extract_json_from_response_ignores_done_prefix():
    text = 'Done.{"status":"ok","artifacts":{"submission_trace.json":{"workflow_stages":[]}}}'

    extracted = BenchmarkEngine._extract_json_from_response(text)

    assert extracted == '{"status":"ok","artifacts":{"submission_trace.json":{"workflow_stages":[]}}}'
