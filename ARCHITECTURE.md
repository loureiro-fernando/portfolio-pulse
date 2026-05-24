# Portfolio-Pulse - Architecture

Living document of the high-level design and the trade-offs made along the way. Keeps the README focused on what the project does; this file explains *why* it is built this way.

## Goals

1. **Demonstrate the Anthropic Required Skill set** for the Mavila AI Agent Engineer role: Managed Agents API, multi-agent orchestration, Agent Skills with evals, MCP connectors, SCIM 2.0, RBAC, OTel.
2. **Look like an enterprise product**, not a sandbox script: Postgres (not SQLite), Docker compose, GitHub Actions CI, pre-commit with `gitleaks`, granular commits, ARCHITECTURE + RUNBOOK + README.
3. **Stay cheap to run** so a recruiter can clone and reproduce in under 15 minutes on their own Anthropic account.

## Non-goals

- Production-ready multi-tenant isolation (no Postgres RLS, no per-tenant encryption keys)
- Real authentication UX (login is dev-only, password check is presence-only)
- Real MCP connectors for PitchBook or Egnyte (mocks live in `app/services/mocks/`)
- High availability (single-process FastAPI; pipeline runs in `BackgroundTasks` and dies if the worker restarts)

## High-level diagram

```
                    +-----------------+
   IdP (Okta/AAD) -->|  /scim/v2/*    |--+
                    +-----------------+  |
                                         v
                    +-----------------+  +---------+    +----------+
  Portcos -- POST -->|  /webhook/{t}  |->|         |--->| Postgres |
                    +-----------------+  | FastAPI |    +----------+
                                         |  +OTel  |
  Dashboard <-- SSE--|  /stream/{t}   |<-|         |
  /dashboard         +-----------------+  +---------+
                                         | calls   |
                                         v         |
                    +-------------------------+    |
                    | Orchestrator            |    |
                    | (BackgroundTask)        |    |
                    +-------------------------+    |
                                  |                |
                                  v                |
              +-------------------------------+    |
              | Anthropic Managed Agents      |    |
              |                               |    |
              |   Coordinator                 |    |
              |     -> AnomalyDetector        |    |
              |     -> ContextBuilder         |    |
              |     -> SeverityClassifier     |    |
              |                               |    |
              +-------------------------------+    |
                       ^         |                 |
       custom_tool_use |         v custom_tool_result
                       |   (host-side dispatch)    |
                  +----+--------------------+      |
                  | tools.dispatch()        |      |
                  | - fetch_history (DB) ---|------+
                  | - compare_peers (DB) ---|------+
                  | - pitchbook_*  (mock)   |
                  | - egnyte_*     (mock)   |
                  | - slack_*  (slack-sdk)  |---> Slack #portfolio-pulse
                  | - get_tenant_policy     |
                  +-------------------------+
```

## Architectural decisions (ADR-light)

### ADR-001: Anthropic Managed Agents over Messages API

**Decision:** use `client.beta.sessions` + `client.beta.agents` (Managed Agents API, Beta `managed-agents-2026-04-01`) instead of the older `client.messages.create()` + manual tool loop.

**Why:** the Mavila JD lists Managed Agents API as a Required Skill. Using it natively (with `multiagent` coordinator + 3 sub-agents) demonstrates fluency. Cost overhead vs Messages API is ~10-20% in tokens (agent system messages get added by the runtime) - acceptable for a demo.

**Trade-off:** Managed Agents is Beta. Event shapes can shift between SDK versions. Mitigated by defensive `getattr` everywhere in `app/agents/orchestrator.py`. We hit two API quirks during the build (tool_use_id vs custom_tool_use_id; usage not in stream events) and fixed them.

### ADR-002: Custom tools wrapping over HTTP MCP

**Decision:** Slack/PitchBook/Egnyte capabilities are exposed to the agent as **custom tools** (`{"type": "custom", ...}`), with their callbacks executing host-side in `app/agents/tools.py:dispatch()`. The stdio Slack MCP server (`app/mcp_servers/slack_server.py`) stays as a portable artifact (with a working `tests/smoke_slack.py`) but is not wired into the agent.

**Why:** Managed Agents accepts MCP servers only via HTTP URL (`mcp_servers[].url`). Wrapping stdio behind a local HTTP shim was extra work that did not pay back enough for the demo timeline. Custom tools are simpler, faster to iterate, and have a critical security benefit: **secrets never enter the cloud container**. The agent sees the tool schema, never the `SLACK_BOT_TOKEN` or DB credentials.

**Trade-off:** the agent cannot be deployed as-is to a Cowork environment that has no access to our host's `tools.dispatch` callback. If we ever go that route, we either (a) expose the same operations behind an HTTP MCP server, or (b) duplicate the agent config with `mcp_toolset` pointing at the new server.

### ADR-003: BackgroundTasks instead of a real queue

**Decision:** `POST /webhook/{tenant_slug}` returns `202 Accepted` and schedules `orchestrator.run_pipeline(...)` via FastAPI `BackgroundTasks`. No Celery, RQ, ARQ, or Dramatiq.

**Why:** keep the dependency surface small. The pipeline takes 20-60s; blocking the request is a bad UX. Real queues add operational overhead (broker, worker, retries, DLQ) that is out of scope for a portfolio demo.

**Trade-off:** if uvicorn restarts mid-pipeline, the run is lost. Acceptable for v0.1.0; a roadmap item for v0.2+.

### ADR-004: In-memory SSE event bus

**Decision:** `app/event_bus.py` keeps one `asyncio.Queue` per tenant in process memory. The webhook and orchestrator `put` events; the SSE endpoint consumes.

**Why:** simplest possible thing that lets the dashboard show progress live.

**Trade-off:** does not survive process restart and does not fan out across workers. The roadmap is **Postgres `LISTEN/NOTIFY`** when this becomes a constraint - the event payload shape stays the same, only the transport changes.

### ADR-005: Hardcoded tenant policies + mocks

**Decision:** `app/services/policies.py` holds severity thresholds per tenant in a Python dict. `app/services/mocks/{pitchbook,egnyte}.py` return hardcoded dicts for the corresponding agent tools.

**Why:** we needed *plausible* data to demonstrate the pipeline, not real-time integrations. Each dict has a TODO comment showing the swap point for a real backend.

**Trade-off:** demo only. Production would back these with a `tenant_policies` table and real API clients.

### ADR-006: JWT for RBAC, SCIM bearer for /scim/v2/*

**Decision:** two distinct auth schemes.

- `/auth/login` issues an 8h JWT signed with `JWT_SECRET`. `@requires_role("gp", "analyst")` decorator validates JWT + role claim.
- `/scim/v2/*` requires `Authorization: Bearer <SCIM_BEARER_TOKEN>` matching env. No JWT - the IdP (Okta, Azure AD) speaks bearer.

**Why:** that is how enterprise IdPs actually integrate. SCIM 2.0 spec assumes shared-secret bearer; user-facing endpoints assume token-per-session. Mixing them would be wrong.

**Trade-off:** in MVP the login password check is presence-only (any non-empty password works for a seeded user). Bcrypt + real password storage is one line away (`bcrypt.checkpw(req.password.encode(), user.password_hash.encode())`) - left as a roadmap item.

### ADR-007: SCIM 2.0 minimum viable, RFC 7644

**Decision:** implement `/scim/v2/Users` (GET list+filter, GET id, POST, PUT, DELETE) and `/scim/v2/Groups` (GET, POST). Schemas follow RFC 7644 shape (`schemas`, `meta`, `Resources`, ListResponse, Error). Filtering supports only `userName eq "x"` for v0.1.0.

**Why:** demonstrate the discipline. A real Okta integration will hit ~80% of the value with this subset. PATCH and complex filters are predictable extensions.

**Trade-off:** PATCH is not supported (Okta uses it for partial updates - they will fall back to PUT). Not a blocker for the demo.

### ADR-008: OpenTelemetry OTLP HTTP exporter

**Decision:** `app/telemetry.py` configures a global TracerProvider with `OTLPSpanExporter` over HTTP to `localhost:4318` (Jaeger all-in-one in docker-compose).

**Why:** HTTP exporter avoids the gRPC dependency tangle (`opentelemetry-exporter-otlp-proto-grpc` works but is heavier). Jaeger is the most recognizable visual for "look, traces" in a demo video.

**Trade-off:** swap to gRPC if you need batching efficiency in production.

### ADR-009: Postgres + raw `Base.metadata.create_all`, no Alembic

**Decision:** schema is created from SQLAlchemy models via `app/scripts/init_db.py`. No migrations framework.

**Why:** MVP. Adding Alembic for a demo with 8 tables creates a long ceremony for zero payoff. README mentions Alembic as a v0.2+ roadmap item.

**Trade-off:** schema changes require drop + recreate (which we did when adding `Group`/`UserGroupMembership` + `User.sector` in Session 3).

## Layering

The codebase is structured in three layers, top-down:

1. **API (`app/main.py`, `app/api/*`)** - thin handlers, request/response shaping, RBAC enforcement.
2. **Services (`app/services/*`, `app/agents/*`)** - domain logic, tool implementations, agent orchestration. Most of the code lives here.
3. **Persistence (`app/models/*`, `app/db.py`)** - SQLAlchemy 2.0 async models + session factory. Stateless.

Cross-cutting:
- `app/event_bus.py` - in-process pub/sub for SSE
- `app/telemetry.py` - OTel setup
- `app/config.py` - pydantic-settings (.env loader)

The agent system has its own internal layering:
- `app/agents/setup.py` - one-time IaC (creates env + agents on Anthropic, persists IDs)
- `app/agents/orchestrator.py` - per-request session lifecycle, tool callback loop, persistence
- `app/agents/tools.py` - schema declarations + host-side dispatch
- `app/agents/prompts.py` - system prompts (separated so they can be tuned without touching code)

## Multi-tenancy story

Everything is keyed by `tenant_id`:
- `Portco.tenant_id` (data ownership)
- `KpiSnapshot.tenant_id`, `Alert.tenant_id`, `AgentRun.tenant_id`
- `User.tenant_id` (and JWT carries `tenant_id` claim)
- `Group.tenant_id`

Filtering by tenant happens in queries (`WHERE tenant_id = ?`). There is **no Postgres RLS** (row-level security) yet - the application is trusted to filter. RLS is a v0.2+ roadmap item.

## What changes when scope grows

| If you need... | Today | Future |
|---|---|---|
| 100+ tenants | Single-process FastAPI | Add a queue (RQ/ARQ); shard event bus; possibly per-tenant Postgres schemas |
| Real auth | dev-only password check | bcrypt verify + password reset flow + OAuth IdP |
| Real MCP for Slack | custom tool callback host-side | HTTP MCP server mount + agent config update |
| Cross-worker SSE | `asyncio.Queue` in-process | Postgres `LISTEN/NOTIFY` (payload shape stays the same) |
| Audit log | application logs | Append-only `audit_log` table + RLS |
| Schema migrations | `init_db.py` drop+recreate | Alembic |
| Cost guardrails | hardcoded `AGENT_MODEL=Haiku` env var | Per-tenant budget table; rate limit at orchestrator |

## File-to-responsibility map

| File | Responsibility |
|---|---|
| `app/main.py` | FastAPI app + lifespan + routers + static mount + webhook + SSE stream + /health |
| `app/api/auth.py` | POST /auth/login (issues JWT) |
| `app/api/admin.py` | RBAC-guarded admin reads (portcos, alerts, agent_runs) with scoping |
| `app/api/scim.py` | SCIM 2.0 Users + Groups (bearer auth) |
| `app/services/rbac.py` | JWT issue/decode + `@requires_role` decorator |
| `app/services/scim_schemas.py` | Pydantic models matching RFC 7644 |
| `app/services/policies.py` | Tenant severity thresholds |
| `app/services/anomaly_data.py` | DB queries for `fetch_history` / `compare_peers` |
| `app/services/mocks/{pitchbook,egnyte}.py` | In-memory fake data for the corresponding tools |
| `app/agents/setup.py` | Idempotent creation of env + 4 agents on Anthropic |
| `app/agents/orchestrator.py` | Session lifecycle, stream loop, tool dispatch, persistence |
| `app/agents/tools.py` | Custom tool schema registry + dispatch |
| `app/agents/prompts.py` | System prompts for the 4 agents |
| `app/mcp_servers/slack_server.py` | Standalone stdio MCP server (portable, not used by the agent) |
| `app/models/entities.py` | SQLAlchemy models |
| `app/models/base.py` | DeclarativeBase + naming convention + created_at/updated_at |
| `app/db.py` | async engine + sessionmaker |
| `app/event_bus.py` | In-memory SSE event bus per tenant |
| `app/telemetry.py` | OTel tracer provider + OTLP HTTP exporter |
| `app/config.py` | pydantic-settings (.env loader) |
| `app/scripts/init_db.py` | Schema creation |
| `app/scripts/seed.py` | Dev data (1 tenant, 3 portcos, 108 KPIs, 3 users, 2 groups) |
| `app/static/dashboard.html` | Single-page dashboard (Alpine + Chart.js + Tailwind via CDN) |
| `skills/portco-anomaly-monitor/` | Agent Skill packaging the pipeline |
| `skills/lp-update-drafter/` | Agent Skill for quarterly LP letter generation |
| `tests/` | Unit tests (no I/O) |
| `cowork.yaml` | Anthropic Cowork manifest |
| `.github/workflows/ci.yml` | GitHub Actions (ruff + pytest) |
| `docker-compose.yml` | Postgres 16 + Jaeger all-in-one |
| `Makefile` | `make up/down/dev/init-db/seed/smoke-slack/test/lint` |

## Threat model (lightweight)

| Threat | Mitigation |
|---|---|
| Secrets committed to repo | `gitleaks` pre-commit hook, `.env` in `.gitignore`, `.agents_config.json` in `.gitignore` |
| Pipeline cost runaway | Hardcoded Haiku in `.env`, `auto_reload` OFF on Anthropic billing, explicit warning in README |
| Cross-tenant data leak via agent | All custom tools take `tenant_id` / `portco_id` from request, never trust LLM-generated IDs as-is (TODO: add validator) |
| SCIM bearer guessable | `SCIM_BEARER_TOKEN` is 32+ chars env-supplied; rotation procedure in RUNBOOK |
| JWT replay after logout | 8h expiry; no refresh tokens. Production would add a revocation list |
| LLM-generated SQL injection | Not applicable - agents never see raw SQL, they call typed tools |

## License

MIT - this is a portfolio project, anyone can read or fork. Real PE work product would not look like this.
