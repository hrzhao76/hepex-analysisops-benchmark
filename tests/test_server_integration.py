import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4
import yaml

import httpx
import pytest

# A2A official client bits (module paths may differ slightly by version)
from a2a.client import A2ACardResolver, A2AClient
from a2a.types import (
    AgentCard,
    MessageSendParams,
    SendMessageRequest,
)

@pytest.fixture(scope="module")
def green_server_process(tmp_path_factory):
    # Setup data dir
    tmpdir = tmp_path_factory.mktemp("green_server_fixture")
    data_dir = tmpdir / "atlas_cache"
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Setup task spec dir for test
    # We need a valid task spec on disk because we communicate via task_dirs
    spec_dir = tmpdir / "specs" / "zpeak_fit"
    spec_dir.mkdir(parents=True, exist_ok=True)
    
    (spec_dir / "task_spec.yaml").write_text(yaml.dump({
        "id": "t001_zpeak_fit",
        "type": "zpeak_fit",
        "mode": "mock",
        "needs_data": False,
        "skim": "2muons",
        "rubric_path": "rubric.yaml"
    }))
    (spec_dir / "rubric.yaml").write_text(yaml.dump({
        "total": 100,
        "gates": [{"id":"g1", "type":"required_fields", "required_fields":["status"]}],
        "rule_checks": []
    }))
    
    env = os.environ.copy()
    env["HEPEX_DATA_DIR"] = str(data_dir)
    env["PYTHONPATH"] = "src" # Ensure src is in pythonpath

    # Start server
    host = "127.0.0.1"
    port = 9002 # Use different port to avoid conflict
    cmd = [sys.executable, "src/server.py", "--host", host, "--port", str(port)]
    
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # Wait for ready
    base_url = f"http://{host}:{port}"
    max_retries = 50
    ready = False
    for _ in range(max_retries):
        try:
            with httpx.Client(timeout=1.0) as client:
                resp = client.get(f"{base_url}/.well-known/agent-card.json")
                if resp.status_code == 200:
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
        
    yield {"base_url": base_url, "data_dir": data_dir, "spec_dir": spec_dir}
    
    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.mark.asyncio
async def test_green_agent_a2a_send_message(green_server_process):
    server_info = green_server_process
    base_url = server_info["base_url"]
    data_dir = server_info["data_dir"]
    spec_dir = server_info["spec_dir"]
    
    # Build EvalRequest JSON payload
    eval_request = {
        "participants": {},
        "config": {
            "data_dir": str(data_dir),
            "task_dirs": [str(spec_dir)], # Use task_dirs pointing to our temp spec
        },
    }

    # Send as A2A "message" with a single text part containing JSON
    send_message_payload = {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": json.dumps(eval_request)}],
            "messageId": uuid4().hex,
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as httpx_client:
        # 1) Resolve agent card
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
        final_agent_card = await resolver.get_agent_card()

        # 2) Create A2A client
        client = A2AClient(httpx_client=httpx_client, agent_card=final_agent_card)

        # 3) Send message
        request = SendMessageRequest(id=str(uuid4()), params=MessageSendParams(**send_message_payload))
        response = await client.send_message(request)

    # Basic response sanity
    resp_json = response.model_dump(mode="json", exclude_none=True)
    assert resp_json is not None

    # Hard proof: run artifacts should exist
    runs_root = data_dir / "runs"
    
    # It might take a moment for the server to write files if it's doing async processing, 
    # but A2A request usually waits for completion unless streaming/async mode is fully decoupled.
    # The current agent implementation seems to `await updater.complete` so it should be done.
    
    assert runs_root.exists(), f"runs/ not created at {runs_root}"

    run_dirs = [p for p in runs_root.iterdir() if p.is_dir()]
    assert len(run_dirs) >= 1, f"No run dirs found in {runs_root}"

    # Pick latest run dir
    run_dir = sorted(run_dirs)[-1]
    task_dir = run_dir / "t001_zpeak_fit"
    assert task_dir.exists(), f"Task dir missing: {task_dir}"

    for fname in ["meta.json", "submission_trace.json", "judge_input.json", "judge_output.json"]:
        assert (task_dir / fname).exists(), f"Missing {fname} under {task_dir}"
