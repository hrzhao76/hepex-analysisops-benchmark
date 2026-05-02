#!/usr/bin/env python3
import argparse
import asyncio
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"

try:
    from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
    from a2a.types import Message, Part, Role, TextPart
    import httpx
except ImportError:
    print("Error: 'a2a-sdk' and 'httpx' are required.")
    print("Please run this script using uv: uv run scripts/reproduce_locally.py ...")
    sys.exit(1)

# Note: EvalRequest is just a dict with {participants, config} - no import needed

# Template for docker-compose
# Note: Double braces {{ }} are used to escape them in Python's .format()
# Port mapping:
#   Both agents use internal port 9009 (AgentBeats standard)
#   Green Agent: mapped to host port 9000 (to avoid conflict)
#   Purple Agent: mapped to host port 9009
#   Inter-container communication uses container names (e.g., purple-agent:9009)
TEMPLATE = """
services:
  green-agent:
    container_name: green-agent
    image: {green_image}
    command: ["--host", "0.0.0.0", "--card-url", "http://localhost:9000/"]
    ports:
      - "9000:9009"
    environment:
      - HEPEX_DATA_DIR=/home/agent/output
      - HEPEX_JUDGE_PROVIDER={judge_provider}
      - HEPEX_OPENAI_MODEL={judge_openai_model}
      - HEPEX_OLLAMA_MODEL={judge_ollama_model}
      - OLLAMA_HOST={ollama_host}
{proxy_env}    volumes:
      - {run_output_dir}:/home/agent/output
      - ./shared_input:/shared/hepex/input
    env_file:
      - .env
    depends_on:
      - purple-agent

  purple-agent:
    container_name: purple-agent
    image: {purple_image}
    command: ["--host", "0.0.0.0", "--card-url", "http://purple-agent:9009/"]
    environment:
      - HEPEX_DATA_DIR=/home/agent/output
      - HEPEX_AGENT_MODEL={agent_model}
{proxy_env}    volumes:
      - {run_output_dir}:/home/agent/output
      - ./shared_input:/shared/hepex/input:ro
    ports:
      - "9009:9009"
    env_file:
      - .env
"""

def _strip_provider_prefix(model_name: str, provider: str) -> str:
    prefix = f"{provider}/"
    return model_name[len(prefix):] if model_name.startswith(prefix) else model_name


def _agent_model_string(provider: str, model_name: str) -> str:
    if "/" in model_name:
        return model_name
    if provider == "openai":
        return f"openai/{model_name}"
    if provider == "ollama":
        return f"ollama/{model_name}"
    return model_name


def _load_task_metadata(task_dir: str) -> tuple[str, str, str]:
    task_spec_path = Path(task_dir) / "task_spec.yaml"
    if not task_spec_path.exists():
        raise FileNotFoundError(f"Task spec not found: {task_spec_path}")

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required to read task_spec.yaml") from exc

    task_spec = yaml.safe_load(task_spec_path.read_text(encoding="utf-8")) or {}
    release = task_spec.get("release")
    dataset = task_spec.get("dataset")
    skim = task_spec.get("skim")
    if not release or not dataset or not skim:
        raise ValueError(
            f"Task spec {task_spec_path} must define release, dataset, and skim for local shared-input runs."
        )
    return str(release), str(dataset), str(skim)


def _generate_mock_secrets_json(task_dir: str) -> str:
    """Generate a GREEN_SECRETS_JSON payload embedding the mock private rubric."""
    import base64
    try:
        import yaml as _yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required for --mock-rubric") from exc

    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))

    from engine.package_loader import load_submission_contract
    from engine.secret_store import SecretStore
    from tasks.task_spec import load_task_spec
    from utils.mock_private_rubrics import hyy_l1_private_rubric

    task_path = (REPO_ROOT / task_dir).resolve()
    task_spec = load_task_spec(task_path)
    contract = load_submission_contract(task_spec)
    contract_hash = SecretStore("").contract_hash(contract)
    rubric_b64 = base64.b64encode(
        _yaml.safe_dump(hyy_l1_private_rubric(), sort_keys=False).encode("utf-8")
    ).decode("utf-8")
    return json.dumps(
        {
            "schema_version": 1,
            "tasks": {
                task_spec.id: {
                    "public_contract_sha256": contract_hash,
                    "private_rubric_yaml_b64": rubric_b64,
                }
            },
            "judge_env": {},
        }
    )


def _inject_mock_secrets_into_env(secrets_json: str, env_file: str = ".env") -> None:
    """Write GREEN_SECRETS_JSON into the .env file, replacing any existing value."""
    env_path = Path(env_file)
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    lines = [l for l in lines if not l.startswith("GREEN_SECRETS_JSON=")]
    lines.append(f"GREEN_SECRETS_JSON={secrets_json}\n")
    env_path.write_text("".join(lines), encoding="utf-8")
    print("Injected mock GREEN_SECRETS_JSON into .env")


def generate_compose(
    green_image,
    purple_image,
    judge_provider,
    judge_openai_model,
    judge_ollama_model,
    agent_model,
    ollama_host,
    run_output_dir,
    proxy=None,
    output_file="docker-compose.yml",
):
    # We only format the image names. Env vars are handled by docker compose reading .env
    if proxy:
        proxy_env = (
            f"      - http_proxy={proxy}\n"
            f"      - https_proxy={proxy}\n"
            f"      - no_proxy=purple-agent,green-agent,localhost,127.0.0.1\n"
            f"      - NO_PROXY=purple-agent,green-agent,localhost,127.0.0.1\n"
        )
    else:
        proxy_env = ""
    content = TEMPLATE.format(
        green_image=green_image,
        purple_image=purple_image,
        judge_provider=judge_provider,
        judge_openai_model=judge_openai_model,
        judge_ollama_model=judge_ollama_model,
        agent_model=agent_model,
        ollama_host=ollama_host,
        run_output_dir=run_output_dir,
        proxy_env=proxy_env,
    )
    with open(output_file, "w") as f:
        f.write(content)
    print(f"Generated {output_file}")

async def wait_for_agent(base_url, label, timeout=60.0):
    deadline = time.time() + timeout
    async with httpx.AsyncClient(timeout=5.0) as httpx_client:
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=base_url)
        attempt = 0
        while time.time() < deadline:
            attempt += 1
            try:
                agent_card = await resolver.get_agent_card()
                print(f"{label} is ready: {agent_card.name} ({agent_card.version})")
                return True
            except Exception:
                await asyncio.sleep(2.0)
        return False


async def trigger_evaluation(
    green_url,
    purple_internal_url,
    task_dir,
    shared_input_dir,
    input_manifest_path,
    persist_payloads,
):
    print(f"Connecting to Green Agent at {green_url}...")
    
    # Construct the EvalRequest payload for the green agent
    eval_request = {
        "participants": {
            "purple_agent": purple_internal_url
        },
        "config": {
            "task_dirs": [task_dir],
            "data_dir": "/home/agent/output",
            "input_access_mode": "local_shared_mount",
            "shared_input_dir": shared_input_dir,
            "input_manifest_path": input_manifest_path,
            "allow_green_download": False,
            "persist_payloads": persist_payloads,
        }
    }

    # 10 min timeout to allow for data download + LLM calls
    async with httpx.AsyncClient(timeout=600.0) as httpx_client:
        # 1. Resolve agent card
        resolver = A2ACardResolver(httpx_client=httpx_client, base_url=green_url)
        try:
            agent_card = await resolver.get_agent_card()
            print(f"Resolved Agent: {agent_card.name} ({agent_card.version})")
        except Exception as e:
            # print(f"Failed to resolve agent card at {green_url}: {e}")
            raise e

        # 2. Send the message
        config = ClientConfig(httpx_client=httpx_client, streaming=False)
        factory = ClientFactory(config)
        client = factory.create(agent_card)
        outbound_msg = Message(
            kind="message",
            role=Role.user,
            parts=[Part(TextPart(kind="text", text=json.dumps(eval_request)))],
            message_id=uuid.uuid4().hex,
        )

        print("Sending EvalRequest...")
        try:
            async for _ in client.send_message(outbound_msg):
                pass
            print("Request sent successfully!")
            return True
        except Exception as e:
            print(f"Failed to send message: {e}")
            return False

def main():
    parser = argparse.ArgumentParser(description="Reproduce the benchmark locally using Docker Compose.")
    parser.add_argument("--green-image", default="ghcr.io/hrzhao76/hepex-analysisops-benchmark:latest", help="Green agent image")
    parser.add_argument("--purple-image", default="ghcr.io/hrzhao76/hepex-analysisops-agents:latest", help="Purple agent image")
    parser.add_argument("--local", action="store_true", help="Use local images (hepex-green-agent-local:v1.1 / hepex-purple-agent-local:v1.1)")
    parser.add_argument("--detach", "-d", action="store_true", help="Run in detached mode (don't stream logs)")
    parser.add_argument("--task-dir", default="tasks_public/t002_hyy_v5_l1", help="Task directory to evaluate")
    parser.add_argument(
        "--llm-provider",
        choices=["ollama", "openai"],
        default="ollama",
        help="LLM backend for local testing. Defaults to ollama.",
    )
    parser.add_argument(
        "--llm-model",
        default="gpt-oss:20b",
        help="Model name for the selected provider. Defaults to gpt-oss:20b.",
    )
    parser.add_argument(
        "--ollama-host",
        default="http://host.docker.internal:11434",
        help="Ollama base URL reachable from the containers.",
    )
    parser.add_argument(
        "--no-persist-payloads",
        action="store_true",
        help="Do not persist eval_request / purple request / purple response payloads into the run directory.",
    )
    parser.add_argument(
        "--proxy",
        default=None,
        help="HTTP/HTTPS proxy URL to inject into containers (e.g. https://127.0.0.1:7890).",
    )
    parser.add_argument(
        "--mock-rubric",
        action="store_true",
        help="Embed a mock private rubric into GREEN_SECRETS_JSON in .env so the green agent can score locally without a real secret store.",
    )

    args = parser.parse_args()
    release, dataset, skim = _load_task_metadata(args.task_dir)
    shared_input_root = Path("shared_input")
    shared_input_host_dir = shared_input_root / release / dataset / skim
    shared_input_host_dir.mkdir(parents=True, exist_ok=True)
    shared_input_dir = f"/shared/hepex/input/{release}/{dataset}/{skim}"
    input_manifest_path = f"{shared_input_dir}/input_manifest.json"

    # Ensure .env exists
    if not os.path.exists(".env"):
        print("Error: .env file not found. Please create one with your API keys.")
        print("Example .env content:")
        print("# For OpenAI mode:")
        print("OPENAI_API_KEY=sk-...")
        print("# For Ollama mode, .env can be empty.")
        sys.exit(1)

    if args.mock_rubric:
        secrets_json = _generate_mock_secrets_json(args.task_dir)
        _inject_mock_secrets_into_env(secrets_json)

    green_img = args.green_image
    purple_img = args.purple_image

    if args.local:
        green_img = "hepex-green-agent:local"
        purple_img = "hepex-purple-agent:local"

    if args.llm_provider == "openai":
        judge_provider = "openai"
        judge_openai_model = _strip_provider_prefix(args.llm_model, "openai")
        judge_ollama_model = "gpt-oss:20b"
        agent_model = _agent_model_string("openai", args.llm_model)
    else:
        judge_provider = "ollama"
        judge_openai_model = "gpt-5"
        judge_ollama_model = _strip_provider_prefix(args.llm_model, "ollama")
        agent_model = _agent_model_string("ollama", args.llm_model)

    # Create per-run output directory to keep runs isolated
    run_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    run_output_path = Path("output") / run_id
    run_output_path.mkdir(parents=True, exist_ok=True)
    run_output_dir = f"./output/{run_id}"
    print(f"Run output directory: {run_output_dir}")

    os.makedirs(shared_input_root, exist_ok=True)

    # 1. Generate docker-compose
    generate_compose(
        green_img,
        purple_img,
        judge_provider=judge_provider,
        judge_openai_model=judge_openai_model,
        judge_ollama_model=judge_ollama_model,
        agent_model=agent_model,
        ollama_host=args.ollama_host,
        run_output_dir=run_output_dir,
        proxy=args.proxy,
    )
    print(
        f"Configured local run with provider={judge_provider}, "
        f"judge_model={judge_ollama_model if judge_provider == 'ollama' else judge_openai_model}, "
        f"agent_model={agent_model}"
    )

    # 2. Start containers
    print("Starting containers...")
    subprocess.run(["docker", "compose", "up", "-d"], check=True)

    try:
        # 3. Wait/Trigger loop
        print("Waiting for agents to boot...")

        purple_ready = asyncio.run(wait_for_agent("http://localhost:9009", "Purple Agent"))
        if not purple_ready:
            print("Purple Agent did not become ready in time.")
            sys.exit(1)
        
        success = False
        for i in range(15):
            print(f"Attempt {i+1}/15 to contact Green Agent...")
            try:
                success = asyncio.run(
                    trigger_evaluation(
                        "http://localhost:9000",
                        "http://purple-agent:9009",
                        args.task_dir,
                        shared_input_dir,
                        input_manifest_path,
                        not args.no_persist_payloads,
                    )
                )
                if success:
                    break
            except Exception as e:
                # unexpected setup errors
                pass 
            
            time.sleep(5)
        
        if not success:
            print("Failed to trigger evaluation after retries.")
            sys.exit(1)

        # 4. Tail logs unless detached
        if not args.detach:
            print("\n" + "="*50)
            print("Streaming logs from containers...")
            print("NOTE: Local shared input is expected under")
            print(f"      ./shared_input/{release}/{dataset}/{skim}/ on your host machine.")
            print("="*50 + "\n")
            subprocess.run(["docker", "compose", "logs", "-f"])

    except KeyboardInterrupt:
        print("\nStopping...")
        
    finally:
        if not args.detach:
            print("Shutting down containers...")
            subprocess.run(["docker", "compose", "down"])

if __name__ == "__main__":
    main()
