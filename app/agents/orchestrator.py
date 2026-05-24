"""Pipeline orchestrator: creates a Managed Agent session, streams events,
dispatches custom tool calls, persists AgentRun + Alert, posts to Slack.

The coordinator agent delegates to 3 specialist sub-agents (anomaly, context,
severity) via the multiagent feature. We don't drive the sequencing - the
coordinator does. We only:
- create the session
- answer custom_tool_use events with results
- mirror progress to our local SSE event bus for the dashboard
- persist usage / final alert after the session goes idle
"""

import asyncio
import contextlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import select

from app.agents import tools
from app.agents.setup import load_config
from app.config import settings
from app.db import SessionLocal
from app.event_bus import emit
from app.models.entities import AgentRun, Alert, Portco
from app.telemetry import get_tracer

tracer = get_tracer("portfolio-pulse.orchestrator")

# USD per million tokens. Update when Anthropic re-prices.
COST_RATES: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {"in": 1.0, "out": 5.0},
    "claude-haiku-4-5": {"in": 1.0, "out": 5.0},
    "claude-sonnet-4-6": {"in": 3.0, "out": 15.0},
    "claude-opus-4-7": {"in": 15.0, "out": 75.0},
}


def _cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    rate = COST_RATES.get(model, {"in": 1.0, "out": 5.0})
    return round((input_tokens * rate["in"] + output_tokens * rate["out"]) / 1_000_000, 6)


async def run_pipeline(
    tenant_slug: str,
    tenant_id: str,
    portco_id: str,
    metric: str,
    value: float,
    period: str,
) -> None:
    """Entry point invoked from the webhook BackgroundTask."""
    cfg = load_config()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = cfg["model"]

    async with SessionLocal() as db:
        portco = (
            await db.execute(select(Portco).where(Portco.id == portco_id))
        ).scalar_one_or_none()
        portco_name = portco.name if portco else portco_id

    user_message = (
        f"KPI event: tenant_slug={tenant_slug}, portco_id={portco_id}, "
        f"metric={metric}, value={value}, period={period}. "
        f"Run the pipeline."
    )

    with tracer.start_as_current_span(
        "portfolio_pulse.pipeline",
        attributes={
            "tenant_slug": tenant_slug,
            "portco_id": portco_id,
            "metric": metric,
            "value": value,
            "period": period,
        },
    ) as root_span:
        session = await client.beta.sessions.create(
            agent=cfg["agents"]["coordinator"]["id"],
            environment_id=cfg["environment_id"],
            title=f"{portco_name} / {metric} / {period}",
        )
        root_span.set_attribute("session_id", session.id)
        await emit(
            tenant_slug,
            {
                "type": "pipeline_started",
                "session_id": session.id,
                "portco_id": portco_id,
                "metric": metric,
                "period": period,
            },
        )

        coordinator_final_text = ""
        # Per-thread usage: thread_id -> {agent_name, input, output, latency_ms}
        thread_usage: dict[str, dict[str, Any]] = {}
        thread_start_ts: dict[str, float] = {}

        async with await client.beta.sessions.events.stream(session.id) as stream:
            await client.beta.sessions.events.send(
                session.id,
                events=[  # type: ignore[list-item]
                    {"type": "user.message", "content": [{"type": "text", "text": user_message}]}
                ],
            )

            async for event in stream:
                etype = event.type

                if etype == "session.thread_created":
                    agent_name = getattr(event, "agent_name", "unknown")
                    thread_id = (
                        getattr(event, "session_thread_id", None) or getattr(event, "id", "") or ""
                    )
                    thread_start_ts[thread_id] = asyncio.get_event_loop().time()
                    thread_usage[thread_id] = {
                        "agent_name": agent_name,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "latency_ms": 0,
                    }
                    await emit(
                        tenant_slug,
                        {"type": "agent_started", "agent_name": agent_name, "thread_id": thread_id},
                    )

                elif etype == "span.model_request_end":
                    usage = getattr(event, "model_usage", None)
                    if usage:
                        tid = getattr(event, "session_thread_id", None)
                        if tid and tid in thread_usage:
                            thread_usage[tid]["input_tokens"] += getattr(usage, "input_tokens", 0)
                            thread_usage[tid]["output_tokens"] += getattr(usage, "output_tokens", 0)

                elif etype == "session.thread_status_idle":
                    agent_name = getattr(event, "agent_name", "unknown")
                    tid = getattr(event, "session_thread_id", None) or ""
                    if tid in thread_start_ts:
                        elapsed_ms = int(
                            (asyncio.get_event_loop().time() - thread_start_ts[tid]) * 1000
                        )
                        if tid in thread_usage:
                            thread_usage[tid]["latency_ms"] = elapsed_ms
                    await emit(
                        tenant_slug,
                        {"type": "agent_completed", "agent_name": agent_name, "thread_id": tid},
                    )

                elif etype == "agent.custom_tool_use":
                    tool_name = getattr(event, "name", "")
                    tool_input = _to_dict(getattr(event, "input", {}))
                    tool_use_id = getattr(event, "id", "")
                    thread_id = getattr(event, "session_thread_id", None)

                    with tracer.start_as_current_span(
                        f"tool.{tool_name}",
                        attributes={"tool.name": tool_name, "session_id": session.id},
                    ):
                        try:
                            result = await tools.dispatch(tool_name, tool_input)
                            is_error = False
                        except Exception as exc:  # noqa: BLE001
                            result = f"error: {exc}"
                            is_error = True

                    result_event: dict[str, Any] = {
                        "type": "user.custom_tool_result",
                        "tool_use_id": tool_use_id,
                        "content": [{"type": "text", "text": result}],
                    }
                    if is_error:
                        result_event["is_error"] = True
                    if thread_id is not None:
                        result_event["session_thread_id"] = thread_id

                    await client.beta.sessions.events.send(
                        session.id,
                        events=[result_event],  # type: ignore[list-item]
                    )

                elif etype == "agent.message":
                    is_coordinator = getattr(event, "session_thread_id", None) is None
                    if is_coordinator:
                        content = getattr(event, "content", []) or []
                        for block in content:
                            if getattr(block, "type", None) == "text":
                                coordinator_final_text += getattr(block, "text", "")

                elif etype == "session.status_idle":
                    stop_reason = getattr(event, "stop_reason", None)
                    stop_type = getattr(stop_reason, "type", None) if stop_reason else None
                    if stop_type != "requires_action":
                        break

                elif etype == "session.status_terminated":
                    break

        await emit(
            tenant_slug,
            {
                "type": "pipeline_completed",
                "session_id": session.id,
                "output": coordinator_final_text,
            },
        )

        verdict = _extract_severity_json(coordinator_final_text)
        await _persist_results(
            tenant_id=tenant_id,
            portco_id=portco_id,
            portco_name=portco_name,
            verdict=verdict,
            coordinator_text=coordinator_final_text,
            thread_usage=thread_usage,
            model=model,
        )

        if verdict and verdict.get("severity") in {"attention", "urgent"}:
            with contextlib.suppress(Exception):
                await tools.post_alert_to_slack(
                    portco_name=portco_name,
                    severity=verdict["severity"],
                    summary=verdict.get("summary", "(no summary)"),
                )

        root_span.set_attribute(
            "severity", verdict.get("severity", "n/a") if verdict else "no_anomaly"
        )


def _to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")


def _extract_severity_json(text: str) -> dict[str, Any] | None:
    """The coordinator's final response includes the SeverityClassifier JSON.

    It may be surrounded by an executive summary. Extract the first JSON object.
    Returns None if no valid JSON was found (i.e. the AnomalyDetector said NORMAL).
    """
    if not text:
        return None
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict) and "severity" in parsed:
            return parsed
    except json.JSONDecodeError:
        return None
    return None


async def _persist_results(
    *,
    tenant_id: str,
    portco_id: str,
    portco_name: str,
    verdict: dict[str, Any] | None,
    coordinator_text: str,
    thread_usage: dict[str, dict[str, Any]],
    model: str,
) -> None:
    async with SessionLocal() as db:
        # 1 AgentRun per thread
        for usage in thread_usage.values():
            db.add(
                AgentRun(
                    tenant_id=tenant_id,
                    agent_name=usage["agent_name"],
                    input_tokens=usage["input_tokens"],
                    output_tokens=usage["output_tokens"],
                    cost_usd=_cost_usd(model, usage["input_tokens"], usage["output_tokens"]),
                    latency_ms=usage["latency_ms"],
                    payload={"model": model},
                )
            )

        if verdict:
            db.add(
                Alert(
                    tenant_id=tenant_id,
                    portco_id=portco_id,
                    severity=verdict.get("severity", "info"),
                    summary=verdict.get("summary", "(no summary)"),
                    context={
                        "rationale": verdict.get("rationale"),
                        "coordinator_text": coordinator_text,
                        "portco_name": portco_name,
                        "ts": datetime.now(UTC).isoformat(),
                    },
                    requires_human=bool(verdict.get("requires_human", False)),
                )
            )

        await db.commit()
