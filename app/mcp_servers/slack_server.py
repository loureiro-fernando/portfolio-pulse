import asyncio
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from slack_sdk.web.async_client import AsyncWebClient

from app.config import settings

SEVERITY_EMOJI: dict[str, str] = {
    "info": ":information_source:",
    "attention": ":warning:",
    "urgent": ":rotating_light:",
}

server: Server = Server("portfolio-pulse-slack")

_client: AsyncWebClient | None = None


def _slack_client() -> AsyncWebClient:
    global _client
    if not settings.slack_bot_token:
        raise RuntimeError("SLACK_BOT_TOKEN not configured")
    if _client is None:
        _client = AsyncWebClient(token=settings.slack_bot_token)
    return _client


async def _resolve_channel_id(name: str) -> str | None:
    client = _slack_client()
    resp = await client.conversations_list(types="public_channel,private_channel")
    channels: list[dict[str, Any]] = resp.get("channels", []) or []
    for ch in channels:
        if ch.get("name") == name:
            channel_id = ch.get("id")
            return str(channel_id) if channel_id else None
    return None


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="read_recent_messages",
            description=("Read recent messages from the configured Slack portfolio channel."),
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "default": 20,
                    },
                },
            },
        ),
        Tool(
            name="post_alert",
            description="Post a portfolio alert to the configured Slack channel.",
            inputSchema={
                "type": "object",
                "properties": {
                    "portco_name": {"type": "string"},
                    "severity": {
                        "type": "string",
                        "enum": ["info", "attention", "urgent"],
                    },
                    "summary": {"type": "string"},
                },
                "required": ["portco_name", "severity", "summary"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "read_recent_messages":
        limit = int(arguments.get("limit", 20))
        channel_name = settings.slack_portfolio_channel
        channel_id = await _resolve_channel_id(channel_name)
        if channel_id is None:
            return [TextContent(type="text", text=f"Channel '{channel_name}' not found")]
        client = _slack_client()
        history = await client.conversations_history(channel=channel_id, limit=limit)
        raw_messages: list[dict[str, Any]] = history.get("messages", []) or []
        messages = [str(m.get("text", "")) for m in raw_messages]
        return [TextContent(type="text", text="\n---\n".join(messages))]

    if name == "post_alert":
        portco_name = str(arguments["portco_name"])
        severity = str(arguments["severity"])
        summary = str(arguments["summary"])
        emoji = SEVERITY_EMOJI[severity]
        text = f"{emoji} *{portco_name}* - {summary}"
        client = _slack_client()
        await client.chat_postMessage(channel=f"#{settings.slack_portfolio_channel}", text=text)
        return [TextContent(type="text", text="posted")]

    raise ValueError(f"Unknown tool: {name}")


async def main() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
