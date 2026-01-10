import argparse
import uvicorn

try:
    import tomllib  # py311+
except ModuleNotFoundError:
    import tomli as tomllib  # py310 fallback

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from executor import Executor


def load_card_from_toml(path: str, url: str) -> AgentCard:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)

    skills = []
    for s in cfg.get("skills", []):
        skills.append(
            AgentSkill(
                id=s.get("id", ""),
                name=s.get("name", ""),
                description=s.get("description", ""),
                tags=s.get("tags", []) or [],
                examples=s.get("examples", []) or [],
            )
        )

    cap_cfg = cfg.get("capabilities", {}) or {}
    caps = AgentCapabilities(streaming=bool(cap_cfg.get("streaming", False)))

    return AgentCard(
        name=cfg.get("name", ""),
        description=cfg.get("description", ""),
        url=url,
        version=cfg.get("version", "0.1.0"),
        default_input_modes=cfg.get("default_input_modes", ["text"]),
        default_output_modes=cfg.get("default_output_modes", ["text"]),
        capabilities=caps,
        skills=skills,
    )


def main():
    parser = argparse.ArgumentParser(description="Run the A2A agent.")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to bind the server")
    parser.add_argument("--port", type=int, default=9001, help="Port to bind the server")
    parser.add_argument("--card-url", type=str, help="URL to advertise in the agent card")
    parser.add_argument("--card-toml", type=str, required=True, help="Path to TOML agent card config")
    args = parser.parse_args()

    url = args.card_url or f"http://{args.host}:{args.port}/"
    agent_card = load_card_from_toml(args.card_toml, url)

    request_handler = DefaultRequestHandler(
        agent_executor=Executor(),
        task_store=InMemoryTaskStore(),
    )
    server = A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=request_handler,
    )
    uvicorn.run(server.build(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
