"""One-time setup: create Cloud environment + 4 Managed Agents (3 specialists + 1 coordinator).

Idempotent: persists IDs to .agents_config.json. Re-running with the file present
no-ops (use --force to recreate).

Run: python -m app.agents.setup
"""

import asyncio
import json
import sys
from pathlib import Path

from anthropic import AsyncAnthropic

from app.agents import prompts, tools
from app.config import settings

CONFIG_PATH = Path(__file__).resolve().parents[2] / ".agents_config.json"


async def main(force: bool = False) -> None:
    if CONFIG_PATH.exists() and not force:
        existing = json.loads(CONFIG_PATH.read_text())
        print(f"Config already at {CONFIG_PATH}. Pass --force to recreate.")
        print(json.dumps(existing, indent=2))
        return

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = settings.agent_model

    env = await client.beta.environments.create(
        name="portfolio-pulse-env",
        config={"type": "cloud", "networking": {"type": "unrestricted"}},
    )
    print(f"environment: {env.id}")

    anomaly = await client.beta.agents.create(
        name="portfolio-pulse-anomaly-detector",
        model=model,
        system=prompts.ANOMALY_DETECTOR,
        tools=tools.TOOL_SCHEMAS["anomaly"],  # type: ignore[arg-type]
    )
    print(f"anomaly agent: {anomaly.id} (v{anomaly.version})")

    context = await client.beta.agents.create(
        name="portfolio-pulse-context-builder",
        model=model,
        system=prompts.CONTEXT_BUILDER,
        tools=tools.TOOL_SCHEMAS["context"],  # type: ignore[arg-type]
    )
    print(f"context agent: {context.id} (v{context.version})")

    severity = await client.beta.agents.create(
        name="portfolio-pulse-severity-classifier",
        model=model,
        system=prompts.SEVERITY_CLASSIFIER,
        tools=tools.TOOL_SCHEMAS["severity"],  # type: ignore[arg-type]
    )
    print(f"severity agent: {severity.id} (v{severity.version})")

    coordinator = await client.beta.agents.create(
        name="portfolio-pulse-coordinator",
        model=model,
        system=prompts.COORDINATOR,
        multiagent={  # type: ignore[arg-type]
            "type": "coordinator",
            "agents": [anomaly.id, context.id, severity.id],
        },
    )
    print(f"coordinator agent: {coordinator.id} (v{coordinator.version})")

    config = {
        "environment_id": env.id,
        "model": model,
        "agents": {
            "anomaly": {"id": anomaly.id, "version": anomaly.version},
            "context": {"id": context.id, "version": context.version},
            "severity": {"id": severity.id, "version": severity.version},
            "coordinator": {"id": coordinator.id, "version": coordinator.version},
        },
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    print(f"\nwrote {CONFIG_PATH}")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"{CONFIG_PATH} not found. Run: python -m app.agents.setup")
    return json.loads(CONFIG_PATH.read_text())


if __name__ == "__main__":
    force = "--force" in sys.argv
    asyncio.run(main(force=force))
