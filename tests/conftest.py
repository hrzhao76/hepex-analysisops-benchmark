import os
import sys
import shutil
import time
import subprocess
import httpx
import pytest
import yaml

def pytest_addoption(parser):
    parser.addoption(
        "--agent-url",
        default=None,
        help="External Agent URL (if provided, skips auto-start)",
    )


@pytest.fixture(scope="session")
def agent(request, tmp_path_factory):
    """
    Agent URL fixture. 
    If --agent-url is provided, uses that.
    Otherwise, starts the server locally.
    """
    url = request.config.getoption("--agent-url")
    if url:
        # Check connection
        try:
            response = httpx.get(f"{url}/.well-known/agent-card.json", timeout=2)
            if response.status_code != 200:
                pytest.exit(f"Agent at {url} returned status {response.status_code}", returncode=1)
        except Exception as e:
            pytest.exit(f"Could not connect to agent at {url}: {e}", returncode=1)
        yield url
        return

    # Start local server
    tmpdir = tmp_path_factory.mktemp("green_session_server")
    data_dir = tmpdir / "data"
    data_dir.mkdir()
    
    env = os.environ.copy()
    env["HEPEX_DATA_DIR"] = str(data_dir)
    env["PYTHONPATH"] = "src" 

    host = "127.0.0.1"
    port = 9009
    cmd = [sys.executable, "src/server.py", "--host", host, "--port", str(port)]
    
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
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
        pytest.exit(f"Failed to start local agent on {base_url}")
        
    yield base_url
    
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()