"""Custom tool definitions + dispatch for Portfolio-Pulse agents.

Each tool has two faces:
- TOOL_SCHEMAS: JSON schemas registered with the Managed Agent at creation time.
- dispatch(): runtime handler invoked when the agent emits agent.custom_tool_use.

The agent never executes these — it asks, we answer via user.custom_tool_result.
"""

import json
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from app.config import settings
from app.services import policies
from app.services.anomaly_data import compare_peers, fetch_history
from app.services.mocks import egnyte, pitchbook

SEVERITY_EMOJI: dict[str, str] = {
    "info": ":information_source:",
    "attention": ":warning:",
    "urgent": ":rotating_light:",
}


TOOL_SCHEMAS: dict[str, list[dict[str, Any]]] = {
    "anomaly": [
        {
            "type": "custom",
            "name": "fetch_history",
            "description": (
                "Fetch the last N KpiSnapshots for a portco/metric, newest first. "
                "Use to establish the recent trend before flagging an anomaly."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "portco_id": {"type": "string"},
                    "metric": {"type": "string"},
                    "limit": {"type": "integer", "default": 12, "minimum": 1, "maximum": 48},
                },
                "required": ["portco_id", "metric"],
            },
        },
        {
            "type": "custom",
            "name": "compare_peers",
            "description": (
                "Compare the portco's latest value for a metric to the sector-peer average "
                "for the same period. Returns peer_avg and delta_pct."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "portco_id": {"type": "string"},
                    "metric": {"type": "string"},
                },
                "required": ["portco_id", "metric"],
            },
        },
    ],
    "context": [
        {
            "type": "custom",
            "name": "slack_read_recent_messages",
            "description": "Read recent messages from the configured Slack portfolio channel.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
                },
            },
        },
        {
            "type": "custom",
            "name": "pitchbook_fetch_company_data",
            "description": (
                "PitchBook company snapshot: sector, stage, valuation, headcount, investors."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"portco_id": {"type": "string"}},
                "required": ["portco_id"],
            },
        },
        {
            "type": "custom",
            "name": "pitchbook_get_peer_set",
            "description": "PitchBook peer companies in the same sector with growth/burn metrics.",
            "input_schema": {
                "type": "object",
                "properties": {"sector": {"type": "string"}},
                "required": ["sector"],
            },
        },
        {
            "type": "custom",
            "name": "egnyte_search_docs",
            "description": (
                "Search internal docs (board decks, financials, HR memos). "
                "Optional portco_id filter narrows results."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "portco_id": {"type": "string"},
                },
                "required": ["query"],
            },
        },
        {
            "type": "custom",
            "name": "egnyte_get_doc_content",
            "description": "Fetch full content of a doc returned by egnyte_search_docs.",
            "input_schema": {
                "type": "object",
                "properties": {"doc_id": {"type": "string"}},
                "required": ["doc_id"],
            },
        },
    ],
    "severity": [
        {
            "type": "custom",
            "name": "get_tenant_policy",
            "description": (
                "Return the tenant's severity thresholds and human-handoff rules. "
                "Apply these to classify the anomaly."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"tenant_slug": {"type": "string"}},
                "required": ["tenant_slug"],
            },
        },
    ],
}


def all_tool_schemas() -> list[dict[str, Any]]:
    """Union of all custom tool schemas (used by the coordinator agent if needed)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for tools in TOOL_SCHEMAS.values():
        for tool in tools:
            if tool["name"] not in seen:
                seen.add(tool["name"])
                out.append(tool)
    return out


_slack_client: AsyncWebClient | None = None


def _slack() -> AsyncWebClient:
    global _slack_client
    if _slack_client is None:
        if not settings.slack_bot_token:
            raise RuntimeError("SLACK_BOT_TOKEN not configured")
        _slack_client = AsyncWebClient(token=settings.slack_bot_token)
    return _slack_client


async def _slack_read_recent_messages(limit: int = 20) -> str:
    client = _slack()
    channels_resp = await client.conversations_list(types="public_channel,private_channel")
    raw_channels: list[dict[str, Any]] = channels_resp.get("channels", []) or []
    channel_id = next(
        (ch["id"] for ch in raw_channels if ch["name"] == settings.slack_portfolio_channel),
        None,
    )
    if channel_id is None:
        return f"channel '{settings.slack_portfolio_channel}' not found"
    history = await client.conversations_history(channel=channel_id, limit=limit)
    raw_messages: list[dict[str, Any]] = history.get("messages", []) or []
    messages = [str(msg.get("text", "")) for msg in raw_messages]
    return "\n---\n".join(messages) if messages else "(no recent messages)"


async def post_alert_to_slack(portco_name: str, severity: str, summary: str) -> str:
    """Used by the orchestrator after SeverityClassifier returns. Not exposed as an agent tool."""
    client = _slack()
    emoji = SEVERITY_EMOJI.get(severity, ":grey_question:")
    text = f"{emoji} *{portco_name}* - {summary}"
    await client.chat_postMessage(channel=f"#{settings.slack_portfolio_channel}", text=text)
    return "posted"


async def dispatch(name: str, args: dict[str, Any]) -> str:
    """Execute a custom tool call and return a JSON-serialized string result.

    Result is always a string (the API expects text content in user.custom_tool_result).
    """
    if name == "fetch_history":
        rows = await fetch_history(args["portco_id"], args["metric"], args.get("limit", 12))
        return json.dumps(rows)

    if name == "compare_peers":
        return json.dumps(await compare_peers(args["portco_id"], args["metric"]))

    if name == "slack_read_recent_messages":
        return await _slack_read_recent_messages(args.get("limit", 20))

    if name == "pitchbook_fetch_company_data":
        return json.dumps(pitchbook.fetch_company_data(args["portco_id"]))

    if name == "pitchbook_get_peer_set":
        return json.dumps(pitchbook.get_peer_set(args["sector"]))

    if name == "egnyte_search_docs":
        return json.dumps(egnyte.search_docs(args["query"], args.get("portco_id")))

    if name == "egnyte_get_doc_content":
        return json.dumps(egnyte.get_doc_content(args["doc_id"]))

    if name == "get_tenant_policy":
        return json.dumps(policies.get_tenant_policy(args["tenant_slug"]))

    raise ValueError(f"unknown tool: {name}")
