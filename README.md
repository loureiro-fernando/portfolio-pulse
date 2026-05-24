# Portfolio-Pulse

[![CI](https://github.com/loureiro-fernando/portfolio-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/loureiro-fernando/portfolio-pulse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)

> Multi-tenant portfolio monitoring platform for private investment firms. Three Anthropic Managed Agents detect anomalies, build context and classify severity, orchestrated by a coordinator agent. Packaged as Agent Skills with SCIM 2.0, RBAC, SSE streaming, OpenTelemetry tracing and a live dashboard.

**Status:** v0.1.0 - feature-complete demo MVP.

## What it does (60 seconds)

1. Portfolio companies push KPIs to `POST /webhook/{tenant_slug}` - returns 202 immediately, pipeline runs in background.
2. A **coordinator agent** spins up an Anthropic Managed Agents session and delegates to three specialists via the `multiagent` feature:
   - **AnomalyDetector** calls `fetch_history` + `compare_peers` to flag deltas vs. history and sector peers.
   - **ContextBuilder** calls `pitchbook_*`, `egnyte_*`, `slack_read_recent_messages` to enrich with documented events.
   - **SeverityClassifier** calls `get_tenant_policy` and outputs a strict JSON verdict (`severity`, `requires_human`, `summary`, `rationale`).
3. Each `agent.custom_tool_use` event triggers a callback host-side; the cloud container never sees `SLACK_BOT_TOKEN` or the DB URL.
4. Per-thread token / latency / cost are persisted to `agent_runs`; the alert lands in `alerts` and is mirrored to `#portfolio-pulse` on Slack when severity is `attention` or `urgent`.
5. **Live dashboard** at `/dashboard/` consumes `GET /stream/{tenant_slug}` (SSE) and shows portfolio heatmap, alert feed, cost burndown and agent activity timeline.
6. Every agent call + tool call shows up as a span in Jaeger (`http://localhost:16686`).
7. **SCIM 2.0** at `/scim/v2/Users` + `/scim/v2/Groups` lets an IdP (Okta, Azure AD) provision/deprovision users via bearer token.
8. **RBAC** on `/admin/*` enforces 3 roles (GP, Analyst, LP). Analyst sees only her sector's portcos.

## Architecture

```
                    +----------------+
   IdP (Okta) ----->| /scim/v2/*     |--+
                    +----------------+  |
                                        v
                    +----------------+  +---------+    +----------+
  Portcos -- POST ->| /webhook/{t}   |->|         |--->| Postgres |
                    +----------------+  | FastAPI |    +----------+
                                        |  +OTel  |
  Dashboard <-- SSE| /stream/{t}    |<-|         |
  /dashboard       +----------------+  +---------+
                                        | calls   |
                                        v         |
                    +-------------------------+   |
                    | Orchestrator            |   |
                    | (BackgroundTask)        |   |
                    +-------------------------+   |
                                  |               |
                                  v               |
              +-------------------------------+   |
              | Anthropic Managed Agents      |   |
              |                               |   |
              |   Coordinator                 |   |
              |     -> AnomalyDetector        |   |
              |     -> ContextBuilder         |   |
              |     -> SeverityClassifier     |   |
              |                               |   |
              +-------------------------------+   |
                       ^         |                |
       custom_tool_use |         v custom_tool_result
                       |   (host-side dispatch)   |
                  +----+--------------------+     |
                  | tools.dispatch()        |     |
                  | - fetch_history (DB) ---+-----+
                  | - compare_peers (DB) ---+-----+
                  | - pitchbook_*  (mock)   |
                  | - egnyte_*     (mock)   |
                  | - slack_*  (slack-sdk)  |---> Slack #portfolio-pulse
                  | - get_tenant_policy     |
                  +-------------------------+
```

See `ARCHITECTURE.md` for ADRs and trade-offs.

## Quickstart

```bash
git clone https://github.com/loureiro-fernando/portfolio-pulse
cd portfolio-pulse

# Setup
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Edit .env: fill ANTHROPIC_API_KEY (portfolio-pulse workspace), SLACK_BOT_TOKEN, SCIM_BEARER_TOKEN

# Infra
make up                  # Postgres on :5432, Jaeger UI on :16686

# Schema + seed
make init-db
python -m app.scripts.seed   # 1 tenant, 3 portcos, 108 KPIs, 3 users, 2 groups

# Create env + 4 agents on Anthropic (idempotent, ~5s, $0)
python -m app.agents.setup

# Run
make dev                 # FastAPI on :8000
```

Open `http://127.0.0.1:8000/dashboard/` and trigger a pipeline:

```bash
# Anomaly case: AcmeCo revenue dropped from 4.5 to 3.1 in 2026-04 (-31%)
curl -X POST http://localhost:8000/webhook/acme \
  -H "Content-Type: application/json" \
  -d '{"portco_id":"portco-1","metric":"revenue","value":3.1,"period":"2026-04"}'
# 202 Accepted -> dashboard shows live agent progress -> ~60s -> Slack alert urgent
```

See `RUNBOOK.md` for daily operations, troubleshooting and secret rotation.

## Coverage of Mavila JD requirements

| Required skill | Location | Status |
|---|---|---|
| Managed Agents API, cloud containers, SSE, multi-agent orchestration | `app/agents/setup.py` (coordinator + 3 sub-agents via `multiagent`), `app/agents/orchestrator.py` (session + stream) | done |
| Tool use (custom tools, host-side dispatch) | `app/agents/tools.py` (8 tools across the 3 agents) | done |
| MCP connectors (Slack real, PitchBook/Egnyte mock) | `app/mcp_servers/slack_server.py` (real stdio), `app/services/mocks/{pitchbook,egnyte}.py` | done |
| Agent Skills (SKILL.md + workflow + evals) | `skills/portco-anomaly-monitor/`, `skills/lp-update-drafter/` (5 evals each) | done |
| SCIM 2.0 (RFC 7644) | `app/api/scim.py` (Users + Groups, bearer auth) | done |
| RBAC | `app/services/rbac.py` (`@requires_role` decorator + JWT), 3 roles seeded (GP/Analyst/LP), portco scoping for Analyst | done |
| OpenTelemetry tracing per agent | `app/telemetry.py` (OTLP HTTP exporter), spans in orchestrator wrap pipeline + per-tool-call | done |
| Cowork manifest | `cowork.yaml` | done |
| Python + REST + JSON + SSE | full stack | done |
| Dashboard (HTML + Alpine.js + Chart.js, no build step) | `app/static/index.html` served at `/dashboard/` | done |

## Project layout

```
app/
  api/
    auth.py             POST /auth/login -> JWT
    admin.py            Role-guarded reads (portcos / alerts / agent_runs) with scoping
    scim.py             SCIM 2.0 Users + Groups (bearer auth)
  agents/
    prompts.py          System prompts for the 4 agents
    tools.py            Custom tool schemas + host-side dispatch
    setup.py            One-time creation of env + 4 agents -> .agents_config.json
    orchestrator.py     Session lifecycle, stream loop, custom_tool_use callback, persist AgentRun + Alert
  mcp_servers/
    slack_server.py     Standalone stdio MCP server (portable artifact)
  models/
    entities.py         Tenant, Portco, KpiSnapshot, Alert, User, AgentRun, Group, UserGroupMembership
    base.py             DeclarativeBase + naming convention + created_at/updated_at
  services/
    rbac.py             JWT issue/decode + @requires_role decorator
    scim_schemas.py     Pydantic models matching RFC 7644
    anomaly_data.py     fetch_history / compare_peers queries
    policies.py         Tenant severity thresholds
    mocks/              In-memory PitchBook + Egnyte stand-ins
  scripts/
    init_db.py          Schema creation
    seed.py             Dev data
  static/
    index.html          Single-page dashboard (Alpine.js + Chart.js + Tailwind via CDN)
  config.py             pydantic-settings (.env loader)
  db.py                 async engine + session factory
  event_bus.py          In-memory SSE event bus per tenant
  telemetry.py          OTel tracer provider + OTLP HTTP exporter
  main.py               FastAPI app: webhook + SSE + /health + mount routers + mount /dashboard
skills/
  portco-anomaly-monitor/  Skill packaging the multi-agent pipeline (SKILL.md + script.py + 5 evals)
  lp-update-drafter/       Skill generating quarterly LP letter with 3 personas (5 evals)
tests/                  63 unit tests (no I/O dependencies)
cowork.yaml             Anthropic Cowork manifest
ARCHITECTURE.md         Design decisions and trade-offs (ADR-light)
RUNBOOK.md              Operations, troubleshooting and secret rotation
CONTRIBUTING.md         Setup + workflow + code style
NEXT_STEPS.md           Resume guide (handoff doc)
```

## Multi-agent design notes

- **Coordinator** holds `multiagent: {type: "coordinator", agents: [...]}`. Delegates sequentially: AnomalyDetector -> ContextBuilder -> SeverityClassifier. Short-circuits if AnomalyDetector says NORMAL.
- **Specialists** are independent Managed Agents (each `agents.create()` returns an `agent_id` + `version` pinned in `.agents_config.json`).
- **Custom tool dispatch loop** lives in `app/agents/orchestrator.py`. On `agent.custom_tool_use`, we look up `tools.dispatch(name, input)`, await the result, and reply with `user.custom_tool_result` carrying the original `session_thread_id`.
- **Persistence happens after the session goes idle.** Per-thread `usage` is fetched via `client.beta.sessions.threads.list()` (the SDK does not surface usage in the event stream).
- **OTel spans** wrap the full pipeline + each tool call.

## Ethics

- No real client data. KPIs are hardcoded synthetic trajectories in `app/scripts/seed.py`; PitchBook / Egnyte stand-ins return canned fixtures from `app/services/mocks/`.
- Pre-commit `gitleaks` blocks secret leaks before commit.
- Repo born fresh - no copying from prior client work.
- Secrets (Anthropic key, Slack token, JWT secret, SCIM bearer, DB credentials) live in `.env` (gitignored). They never enter the cloud container - the agent only sees tool schemas, never the credentials behind them.

## Why mocked data (and not public real data)

A reasonable question: SEC EDGAR, yfinance and similar APIs would let me feed real public-company numbers into the pipeline. I deliberately chose synthetic mocks instead. Three reasons:

1. **Wrong use case.** PE/VC firms monitor **private** portcos with monthly/weekly operational KPIs (MRR, CAC, churn, runway). Public-market filings are quarterly accounting metrics (revenue, EBITDA, net income) for **listed** companies. Wiring EDGAR into a tool designed for a PE workflow would look like a mismatch to anyone in the space - and Mavila invests in private companies.
2. **Wrong cadence.** The pipeline was designed for continuous monitoring (webhook in -> 202 Accepted -> agent runs in ~60s, dashboard updates live). Public filings land every 90 days. Demo would show an empty dashboard 89 days out of every quarter, or require a fake cadence layer on top - which is exactly what mocks already are.
3. **Determinism matters for a demo.** The seeded `TRAJECTORIES` in `app/scripts/seed.py` were calibrated to look like plausible early-stage SaaS / Healthtech / Fintech curves, with a deliberate revenue collapse and churn spike on AcmeCo in the latest period. Anyone cloning the repo gets the same anomaly, the same alert and the same Slack message - so the recruiter sees the pipeline succeed on the first try, not "sometimes the model decides this is fine".

**Production path is short.** The mocks in `app/services/mocks/{pitchbook,egnyte}.py` and the seed in `app/scripts/seed.py` are isolated behind the same interfaces the real clients would use. Swapping them for live PitchBook / Egnyte / portco-reported data is an integration job (real API keys, real HTTP clients, real data normalization), not an architecture change.

## What's NOT in this MVP

- Real password verification (login is dev-only - any non-empty password works for seeded users; `bcrypt.checkpw` is one line away)
- SCIM PATCH (only GET/POST/PUT/DELETE; Okta falls back to PUT gracefully)
- Postgres RLS for tenant isolation (application-layer filtering only)
- Schema migrations via Alembic (using `Base.metadata.create_all`)
- Real PitchBook / Egnyte clients (mocks live in `app/services/mocks/`)
- Live HTTP MCP server for Slack (stdio version exists; custom-tools wrapping is what the agent actually uses - see ADR-002 in `ARCHITECTURE.md`)
- Multi-worker SSE fan-out (in-memory event bus; Postgres `LISTEN/NOTIFY` is the roadmap)
- Persistent background jobs (uses FastAPI `BackgroundTasks`; if uvicorn restarts mid-run, the pipeline is lost)

See `ARCHITECTURE.md` for full ADRs and `RUNBOOK.md` for runtime constraints.

## Cost

| Phase | Model | Approx cost per run |
|---|---|---|
| Dev / iteration | Haiku 4.5 | $0.06 per anomaly pipeline run |
| Demo recording | Sonnet 4.6 | $0.20 per anomaly pipeline run |

Default in `.env.example` is Haiku. Switch to Sonnet only when recording the Loom video.

## License

MIT - see [LICENSE](LICENSE).
