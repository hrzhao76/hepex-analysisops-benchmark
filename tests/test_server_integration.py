import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import MessageSendParams, SendMessageRequest


ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="module")
def green_server_process(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("green_server_fixture") / "atlas_cache"
    data_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["HEPEX_DATA_DIR"] = str(data_dir)
    env["PYTHONPATH"] = "src"

    host = "127.0.0.1"
    port = 9002
    proc = subprocess.Popen(
        [sys.executable, "src/server.py", "--host", host, "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    base_url = f"http://{host}:{port}"
    ready = False
    for _ in range(50):
        try:
            with httpx.Client(timeout=1.0) as client:
                if client.get(f"{base_url}/.well-known/agent-card.json").status_code == 200:
                    ready = True
                    break
        except Exception:
            pass
        time.sleep(0.1)

    if not ready:
        proc.kill()
        stdout, stderr = proc.communicate()
        print("Server stdout:", stdout.decode())
        print("Server stderr:", stderr.decode())
        raise RuntimeError("Server failed to start")

    yield {"base_url": base_url, "data_dir": data_dir}

    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.asyncio
async def test_green_agent_a2a_send_message_public_task(green_server_process):
    server_info = green_server_process
    eval_request = {
        "participants": {"purple_agent": "http://unused.example.com"},
        "config": {
            "data_dir": str(server_info["data_dir"]),
            "task_dirs": [str(ROOT / "tasks_public" / "t001_zpeak_fit")],
            "task_overrides": {"t001_zpeak_fit": {"mode": "mock"}},
        },
    }
    payload = {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": json.dumps(eval_request)}],
            "messageId": uuid4().hex,
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=server_info["base_url"])
        client = A2AClient(httpx_client=httpx_client, agent_card=await resolver.get_agent_card())
        request = SendMessageRequest(id=str(uuid4()), params=MessageSendParams(**payload))
        response = await client.send_message(request)

    assert response.model_dump(mode="json", exclude_none=True) is not None
    runs_root = server_info["data_dir"] / "runs"
    assert runs_root.exists()

    run_dir = sorted(path for path in runs_root.iterdir() if path.is_dir())[-1]
    task_dir = run_dir / "t001_zpeak_fit"
    for filename in ["meta.json", "submission_bundle_raw.json", "submission_trace.json", "judge_input.json", "judge_output.json"]:
        assert (task_dir / filename).exists(), f"Missing {filename} under {task_dir}"
