# Portfolio-Pulse

[![CI](https://github.com/loureiro-fernando/portfolio-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/loureiro-fernando/portfolio-pulse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)

> Multi-tenant portfolio monitoring platform for private investment firms. Three Anthropic Managed Agents detect anomalies, build context and classify severity. Packaged as Agent Skills with SCIM, RBAC, SSE streaming and OpenTelemetry tracing per tenant.

**Status:** v0.1.0 - Session 1 MVP (ingestion + SSE + Slack MCP). Multi-agent pipeline lands in Session 2.

## What it does (60 seconds)

1. Portfolio companies push KPIs to `POST /webhook/{tenant_slug}`
2. Three Managed Agents will run in sequence (Session 2):
   - **Anomaly Detector** - flags deltas vs. history and peer set
   - **Context Builder** - enriches via MCP (Slack, PitchBook mock, Egnyte mock)
   - **Severity Classifier** - decides info / attention / urgent + human handoff
3. Dashboard streams alerts live via `GET /stream/{tenant_slug}` (SSE)
4. Cost, latency and tokens per agent per tenant via OpenTelemetry / Jaeger

## Architecture (current)

```
                 POST /webhook/{tenant}         GET /stream/{tenant}
                          |                              ^
                          v                              |
                   FastAPI app (app/main.py) ---- in-memory event bus
                          |
                          v
                   Postgres (Session 2: persist KPIs, alerts, agent runs)

  Slack MCP server (app/mcp_servers/slack_server.py)
    - read_recent_messages
    - post_alert
```

## Quickstart

```bash
git clone https://github.com/loureiro-fernando/portfolio-pulse
cd portfolio-pulse

# Setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env and fill ANTHROPIC_API_KEY and SLACK_BOT_TOKEN

# Infra
make up                  # Postgres on :5432, Jaeger UI on :16686
make init-db             # Creates 6 tables

# Run
make dev                 # FastAPI on :8000
```

Test the flow in 3 terminals:

```bash
# Terminal 1 - server
make dev

# Terminal 2 - open SSE stream
curl -N http://localhost:8000/stream/acme

# Terminal 3 - push KPI
curl -X POST http://localhost:8000/webhook/acme \
  -H "Content-Type: application/json" \
  -d '{"portco_id":"portco-1","metric":"revenue","value":150000,"period":"2026-04"}'

# Expected: terminal 2 prints the event immediately

# Slack smoke test (posts to your #portfolio-pulse channel)
make smoke-slack
```

## Coverage of Mavila JD requirements

| Required skill | Location | Session |
|---|---|---|
| Managed Agents API, cloud containers, SSE | `app/main.py` (SSE), `app/agents/` (TBD) | 1 partial / 2 |
| Agent Skills (SKILL.md + evals) | `skills/portco-anomaly-monitor/` (TBD) | 3 |
| MCP connectors (Slack, PitchBook, Egnyte) | `app/mcp_servers/slack_server.py` (real) | 1 / 2 |
| SCIM 2.0 + RBAC | `app/api/scim.py`, `app/api/admin.py` (TBD) | 2 / 3 |
| OpenTelemetry tracing per agent | OTel spans + cost attrs (TBD) | 2 |
| Python + REST + JSON + SSE | full stack | 1 |

## Project layout

```
app/
  api/              REST endpoints (SCIM, admin) - Session 2/3
  agents/           AnomalyDetector, ContextBuilder, SeverityClassifier - Session 2
  mcp_servers/      Slack (real), PitchBook (mock), Egnyte (mock) - Session 1/2
  models/           SQLAlchemy entities: Tenant, Portco, KpiSnapshot, Alert, User, AgentRun
  services/         Domain logic - Session 2
  scripts/          init_db.py and seed.py
  config.py         pydantic-settings (.env loader)
  db.py             async engine + session factory
  main.py           FastAPI app with webhook + SSE
skills/             Agent Skills (SKILL.md + evals) - Session 3
tests/              Unit + smoke tests
```

## Ethics

- No real client data anywhere. Faker-generated everywhere.
- Pre-commit `gitleaks` blocks any secret leak before commit.
- Repo born fresh - no copying from prior client work.

## What's NOT in this MVP

- Multi-agent pipeline (Session 2)
- Real RBAC and SCIM (Session 2/3)
- Dashboard with live updates (Session 3)
- Cost burndown charts (Session 3)
- Agent Skills with eval suites (Session 3)
- `cowork.yaml` manifest (Session 3)

See `BACKLOG_portfolio-pulse.md` (private) for full scope and trade-offs.

## License

MIT - see [LICENSE](LICENSE).
