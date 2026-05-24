# Portfolio-Pulse

[![CI](https://github.com/loureiro-fernando/portfolio-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/loureiro-fernando/portfolio-pulse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)

> Multi-tenant portfolio monitoring platform for private investment firms. Three Anthropic Managed Agents detect anomalies, build context and classify severity, orchestrated by a coordinator agent. Packaged with SCIM, RBAC, SSE streaming and OpenTelemetry tracing per tenant.

**Status:** v0.2.0 - Session 2 (multi-agent pipeline + custom tools + OTel + persistence). SCIM, dashboard, Agent Skills land in Session 3.

## What it does (60 seconds)

1. Portfolio companies push KPIs to `POST /webhook/{tenant_slug}` - returns 202 immediately, pipeline runs in background.
2. A **coordinator agent** spins up a Managed Agents session and delegates to three specialists via the multi-agent feature:
   - **AnomalyDetector** - calls `fetch_history` and `compare_peers` to flag deltas vs. history and sector peer set.
   - **ContextBuilder** - calls `pitchbook_*`, `egnyte_search_docs` / `egnyte_get_doc_content`, and `slack_read_recent_messages` to enrich the anomaly with documented events and human chatter.
   - **SeverityClassifier** - calls `get_tenant_policy` and outputs a strict JSON verdict (`severity`, `requires_human`, `summary`, `rationale`).
3. Each `agent.custom_tool_use` event triggers a callback in our app - the secret-bearing code (Slack token, DB queries, mocks) runs on our side, never inside the cloud container.
4. Per-thread token / latency / cost are persisted to `agent_runs`; the alert lands in `alerts` and is mirrored to `#portfolio-pulse` on Slack when severity is `attention` or `urgent`.
5. Dashboard receives live progress (`pipeline_started`, `agent_started`, `agent_completed`, `pipeline_completed`) via `GET /stream/{tenant_slug}` (SSE).
6. Every agent call + tool call shows up as a span in Jaeger (`http://localhost:16686`).

## Architecture

```
POST /webhook/{tenant}                            GET /stream/{tenant}
       |                                                  ^
       v                                                  |
   FastAPI -- persist KpiSnapshot -- emit kpi_received -- |
       |                                                  |
       v (BackgroundTask)                                 |
   Orchestrator                                           |
       |                                                  |
       v                                                  |
   beta.sessions.create(agent=coordinator) ─────────────► |
       |                                                  |
   stream events ◄────────── Anthropic Managed Agents ────┤
       |                              |                   |
       |    (multi-agent feature)     v                   |
       |              ┌─ AnomalyDetector ──┐              |
       |              ├─ ContextBuilder  ──┤  cloud       |
       |              └─ SeverityClassifier┘  container   |
       |                                                  |
       v agent.custom_tool_use                            |
   tools.dispatch(name, input) ─► host-side execution:    |
       - fetch_history / compare_peers (Postgres)         |
       - pitchbook / egnyte mocks (in-memory)             |
       - slack_read_recent_messages (slack-sdk)           |
       - get_tenant_policy (in-memory)                    |
       ─► user.custom_tool_result back to session         |
       |                                                  |
       v session.status_idle (terminal)                   |
   persist AgentRun per thread + Alert + post_alert_to_slack
   emit pipeline_completed ───────────────────────────────┘
```

**Why custom-tools-as-callbacks instead of MCP servers in the agent config:** Managed Agents accepts MCP servers only via HTTP URL (`mcp_servers[].url`). Our Slack MCP server is stdio-based. Wrapping the same operations as custom tools (whose callbacks run host-side in our orchestrator) lets us keep the stdio server as a portable artifact (see `app/mcp_servers/slack_server.py` + `tests/smoke_slack.py`) while still exposing the capability to the agent. Secrets stay host-side - the cloud container never sees `SLACK_BOT_TOKEN` or the DB connection string.

## Quickstart

```bash
git clone https://github.com/loureiro-fernando/portfolio-pulse
cd portfolio-pulse

# Setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env: fill ANTHROPIC_API_KEY (portfolio-pulse workspace) and SLACK_BOT_TOKEN

# Infra
make up                  # Postgres on :5432, Jaeger UI on :16686
make init-db             # Creates 6 tables

# Seed test data (1 tenant, 3 portcos, 12 months of KPIs each)
python -m app.scripts.seed

# One-time: create Cloud environment + 4 agents on Anthropic
# Persists IDs to .agents_config.json (gitignored)
python -m app.agents.setup

# Run
make dev                 # FastAPI on :8000
```

Test the flow in 3 terminals:

```bash
# Terminal 1 - server
make dev

# Terminal 2 - open SSE stream
curl -N http://localhost:8000/stream/acme

# Terminal 3 - push KPI (revenue collapse for AcmeCo in 2026-04)
curl -X POST http://localhost:8000/webhook/acme \
  -H "Content-Type: application/json" \
  -d '{"portco_id":"portco-1","metric":"revenue","value":3.1,"period":"2026-04"}'

# Webhook returns 202 immediately. Terminal 2 streams:
#   kpi_received
#   pipeline_started (session_id)
#   agent_started (AnomalyDetector)
#   agent_completed (AnomalyDetector)
#   agent_started (ContextBuilder)
#   agent_completed (ContextBuilder)
#   agent_started (SeverityClassifier)
#   agent_completed (SeverityClassifier)
#   pipeline_completed (final coordinator output)
# Slack channel #portfolio-pulse receives the alert if severity >= attention.

# Jaeger UI - see spans per agent + per tool call
open http://localhost:16686
```

## Coverage of Mavila JD requirements

| Required skill | Location | Status |
|---|---|---|
| Managed Agents API, cloud containers, SSE, multi-agent orchestration | `app/agents/setup.py` (coordinator + 3 sub-agents via `multiagent` feature), `app/agents/orchestrator.py` (session + stream) | Session 2 - **done** |
| Tool use (custom tools) | `app/agents/tools.py` (8 tools, dispatched host-side) | Session 2 - **done** |
| MCP connectors (Slack real, PitchBook/Egnyte mock) | `app/mcp_servers/slack_server.py` (real stdio), `app/services/mocks/{pitchbook,egnyte}.py` | Session 1/2 - **done** |
| OpenTelemetry tracing per agent | `app/telemetry.py` (OTLP HTTP exporter), spans in orchestrator wrap pipeline + per-tool-call | Session 2 - **done** |
| Agent Skills (SKILL.md + evals) | `skills/portco-anomaly-monitor/` | Session 3 - planned |
| SCIM 2.0 + RBAC | `app/api/scim.py`, `app/api/admin.py` | Session 3 - planned |
| Python + REST + JSON + SSE | full stack | Session 1 - **done** |
| Cowork manifest | `cowork.yaml` | Session 3 - planned |

## Project layout

```
app/
  api/                REST endpoints (SCIM, admin) - Session 3
  agents/
    prompts.py        System prompts for 4 agents (3 specialists + 1 coordinator)
    tools.py          Custom tool schemas + host-side dispatch
    setup.py          One-time creation of environment + 4 agents -> .agents_config.json
    orchestrator.py   Session lifecycle, stream loop, custom_tool_use callback, persist AgentRun + Alert
  mcp_servers/        Slack MCP stdio server (portable artifact)
  models/             SQLAlchemy entities: Tenant, Portco, KpiSnapshot, Alert, User, AgentRun
  services/
    anomaly_data.py   fetch_history, compare_peers queries against Postgres
    policies.py       Tenant severity thresholds (hardcoded for MVP)
    mocks/            In-memory PitchBook + Egnyte stand-ins
  scripts/            init_db.py, seed.py
  config.py           pydantic-settings (.env loader)
  db.py               async engine + session factory
  event_bus.py        In-memory SSE event bus per tenant
  telemetry.py        OTel tracer provider + OTLP HTTP exporter
  main.py             FastAPI app: webhook (BackgroundTask -> orchestrator), SSE stream, /health
skills/               Agent Skills (Session 3)
tests/                Unit + smoke tests (45 tests, no I/O dependencies)
```

## Multi-agent design notes

- **Coordinator agent** holds the `multiagent: {type: "coordinator", agents: [...]}` field. It delegates sequentially: AnomalyDetector -> ContextBuilder -> SeverityClassifier. Short-circuits if AnomalyDetector says NORMAL.
- **Specialist agents** are independent Managed Agents (each `agents.create()` returns an `agent_id` + `version` we pin in `.agents_config.json`). Updates to a specialist bump its version; the coordinator pins its roster, so a new specialist version requires a coordinator update too.
- **Custom tool dispatch loop** is in `app/agents/orchestrator.py`. On `agent.custom_tool_use`, we look up `tools.dispatch(name, input)`, await the result, and reply with `user.custom_tool_result` carrying the original `session_thread_id` so the right thread receives it.
- **Persistence happens after the session goes idle.** We accumulate `model_usage` from `span.model_request_end` events per thread, then write one `AgentRun` per thread with computed `cost_usd`. The final coordinator text is parsed for the SeverityClassifier JSON (regex match on the first object containing a `severity` key) and persisted as an `Alert`.
- **OTel spans** wrap the full pipeline + each tool call. Token / latency / cost attrs land on the model-request-end events; we mirror them into Jaeger via the `tracer.start_as_current_span` context manager.

## Ethics

- No real client data anywhere. Faker-generated everywhere; mocks are obviously fake.
- Pre-commit `gitleaks` blocks secret leaks before commit.
- Repo born fresh - no copying from prior client work.
- Secrets (Anthropic key, Slack token, DB credentials) live in `.env` (gitignored). They never enter the cloud container - the agent only sees the tool schemas, not the credentials behind them.

## What's NOT in this MVP

- SCIM 2.0 + RBAC (Session 3)
- Dashboard UI with live SSE consumption (Session 3)
- Cost burndown chart (Session 3)
- Agent Skills with eval suites (Session 3)
- `cowork.yaml` manifest (Session 3)
- HTTP MCP transport for Slack (current path uses host-side callback wrapping; the stdio server stays as a portable artifact)

See `BACKLOG_portfolio-pulse.md` (private) for full scope and trade-offs.

## License

MIT - see [LICENSE](LICENSE).
