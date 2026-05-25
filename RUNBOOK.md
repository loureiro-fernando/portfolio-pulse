# Portfolio-Pulse - Runbook

Operational playbook for the demo. Covers cold start, common failures, and rotation procedures.

## Cold start (clean machine)

```bash
# 1. Prereqs (one-time)
brew install python@3.12 pre-commit gitleaks
brew install --cask docker-desktop
open -a Docker     # wait for whale icon to settle

# 2. Clone
git clone https://github.com/loureiro-fernando/portfolio-pulse ~/projects_coding/portfolio-pulse
cd ~/projects_coding/portfolio-pulse

# 3. Python env + deps
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install

# 4. Fill secrets (NEVER commit .env)
cp .env.example .env
# Edit .env, fill ANTHROPIC_API_KEY (cap at $30 in Anthropic console),
# SLACK_BOT_TOKEN, JWT_SECRET, WEBHOOK_BEARER_TOKEN and SCIM_BEARER_TOKEN

# 5. Infra
make up                    # postgres :5432 + jaeger :16686

# 6. Schema + seed
make init-db
python -m app.scripts.seed

# 7. Create the 4 Managed Agents on Anthropic (idempotent, ~5s, $0)
python -m app.agents.setup

# 8. Run
make dev                   # uvicorn :8000
# Dashboard: http://127.0.0.1:8000/dashboard/
# Jaeger:    http://localhost:16686
```

## Daily start (everything already installed)

```bash
cd ~/projects_coding/portfolio-pulse
source .venv/bin/activate
make up
make dev
```

## Daily stop

```bash
# Ctrl+C the uvicorn process
make down                  # stops postgres + jaeger
```

## Trigger a test pipeline run

```bash
# Anomaly case (AcmeCo revenue drops 31% in 2026-04)
curl -X POST http://localhost:8000/webhook/acme \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: $WEBHOOK_BEARER_TOKEN" \
  -d '{"portco_id":"portco-1","metric":"revenue","value":3.1,"period":"2026-04"}'
# Expected: 202 + ~$0.06 spent + Slack alert + 4 AgentRuns + 1 Alert urgent + 12 Jaeger spans

# Normal case (BetaHealth steady growth)
curl -X POST http://localhost:8000/webhook/acme \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: $WEBHOOK_BEARER_TOKEN" \
  -d '{"portco_id":"portco-2","metric":"revenue","value":3.7,"period":"2026-05"}'
# Expected: 202 + pipeline runs but no alert (AnomalyDetector says NORMAL)

# Burn spike (GammaFin)
curl -X POST http://localhost:8000/webhook/acme \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: $WEBHOOK_BEARER_TOKEN" \
  -d '{"portco_id":"portco-3","metric":"burn","value":9.5,"period":"2026-05"}'
```

## Authenticated routes (admin + SCIM)

```bash
# Login as GP (seeded dev password: dev)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"gp@acme.test","password":"dev"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')

# Use the token on admin endpoints
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/portcos
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/admin/alerts

# Analyst sees only her sector's portcos
ANALYST_TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"analyst@acme.test","password":"dev"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
curl -H "Authorization: Bearer $ANALYST_TOKEN" http://localhost:8000/admin/portcos
# Expect only SaaS portcos (AcmeCo)

# SCIM list (uses SCIM_BEARER_TOKEN, not JWT)
curl -H "Authorization: Bearer $SCIM_BEARER_TOKEN" \
  http://localhost:8000/scim/v2/Users

# SCIM create user (Okta would call this on provisioning)
curl -X POST http://localhost:8000/scim/v2/Users \
  -H "Authorization: Bearer $SCIM_BEARER_TOKEN" \
  -H "Content-Type: application/scim+json" \
  -d '{
    "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
    "userName": "newuser@acme.test",
    "active": true
  }'
```

## Rotate secrets (you should do this any time a value lands in any chat/log)

### Anthropic API key

1. https://console.anthropic.com/settings/keys
2. Delete `portfolio-pulse-dev`
3. Create new with same name, copy value (shown once)
4. `nano .env` and update `ANTHROPIC_API_KEY=`
5. Restart `make dev` (settings reload on import)
6. **No agent re-creation needed** - the existing `agent_id`s in `.agents_config.json` belong to your workspace, the key just authenticates the API

### Slack bot token

1. https://api.slack.com/apps/A0B5E31ALLF/install-on-team
2. "Reinstall to Workspace" (rotates the bot token)
3. Update `SLACK_BOT_TOKEN=` in `.env`
4. Restart `make dev`

### JWT secret

1. Generate new: `python -c 'import secrets; print(secrets.token_urlsafe(48))'`
2. Update `JWT_SECRET=` in `.env`
3. Restart `make dev`
4. **All existing tokens invalidate** - users must re-login

### Webhook bearer

1. Generate new: same as JWT
2. Update `WEBHOOK_BEARER_TOKEN=` in `.env`
3. Restart `make dev`
4. Update upstream portfolio-company webhook senders

### SCIM bearer

1. Generate new: same as JWT
2. Update `SCIM_BEARER_TOKEN=` in `.env`
3. Restart `make dev`
4. Update the value on the IdP (Okta/Azure AD) so future SCIM calls authenticate

## Troubleshooting

### `make up` fails: "port 5432 already in use"

```bash
# Find what is bound to 5432
lsof -iTCP:5432 -sTCP:LISTEN
# Usually a host Postgres install. Either stop it (brew services stop postgresql)
# or change docker-compose.yml port mapping to "5433:5432" and DATABASE_URL accordingly.
```

### Webhook returns 404 "unknown tenant"

```bash
# Seed never ran or DB was reset. Re-seed:
python -m app.scripts.seed
```

### `python -m app.agents.setup` fails with `FileExistsError` or "already exists"

```bash
# Setup is idempotent (refuses to recreate). To force recreate:
python -m app.agents.setup --force
# Or delete and re-run:
rm .agents_config.json
python -m app.agents.setup
```

### Pipeline runs but no Slack alert

Two common causes:

1. **Severity was `info`** - by design we only post `attention` + `urgent`. Check `SELECT severity FROM alerts ORDER BY id DESC LIMIT 1;`.
2. **Bot is not in the channel** - in Slack run `/invite @portfolio-pulse-bot` in `#portfolio-pulse`.

### Pipeline stuck "in progress"

```bash
# Check FastAPI logs (terminal where make dev runs) for the orchestrator error.
# Most likely: tool dispatch raised. The orchestrator catches and replies with an error
# tool_result, so the agent should continue. If it doesn't:

# Check the session status on Anthropic:
python -c "
import asyncio
from anthropic import AsyncAnthropic
from app.config import settings

async def m():
    c = AsyncAnthropic(api_key=settings.anthropic_api_key)
    sess = await c.beta.sessions.retrieve('<SESSION_ID_FROM_SSE>')
    print(sess.status, sess.stop_reason if hasattr(sess, 'stop_reason') else None)
asyncio.run(m())
"
```

### Spans not appearing in Jaeger

```bash
# Confirm Jaeger is up + reachable
docker compose ps
curl http://localhost:16686/api/services
# Should return {"data":["portfolio-pulse"],...}

# If empty, the exporter never sent. Check OTEL_EXPORTER_OTLP_ENDPOINT in .env
# (should be http://localhost:4318, not 4317 - we use HTTP, not gRPC).
```

### `pip install -e ".[dev]"` fails with `greenlet` missing

This was fixed in v0.1.0 by changing the dep to `sqlalchemy[asyncio]>=2.0` (which puts greenlet under it). If you see it, you are on an older revision - `git pull` and reinstall.

### CI vermelho com "missing field" errors at import time

This happens when a new required field is added to `Settings` without updating `tests/conftest.py`. The conftest seeds dummy env vars before tests import `app.*`; add new fields there too.

### Slack bot lost permission (`missing_scope`)

Bot was reinstalled and lost a scope. Add the missing scope (`channels:read`, `channels:history`, `chat:write`) in api.slack.com -> OAuth & Permissions -> reinstall.

## Cost monitoring

```bash
# Pipeline run cost is logged per-thread in agent_runs.
docker compose exec -T postgres psql -U pulse -d portfolio_pulse -c \
  "SELECT agent_name, SUM(cost_usd) AS total FROM agent_runs GROUP BY agent_name ORDER BY total DESC;"

# Total spend (this DB):
docker compose exec -T postgres psql -U pulse -d portfolio_pulse -c \
  "SELECT ROUND(SUM(cost_usd)::numeric, 4) AS total_usd FROM agent_runs;"
```

## Reset everything (nuclear)

```bash
# Drop data
make down
docker volume rm portfolio-pulse_pgdata

# Drop Anthropic agents (caution: shared with other clones on same key)
rm .agents_config.json
# Then re-create via: python -m app.agents.setup

# Start fresh
make up && make init-db && python -m app.scripts.seed && python -m app.agents.setup && make dev
```

## When something is on fire on demo day

1. **Slack channel went silent**: re-invite the bot (`/invite @portfolio-pulse-bot`)
2. **Anthropic 401**: key was revoked; rotate per "Rotate secrets" above
3. **Anthropic 429**: rate limit hit; switch to Haiku in `.env` (`AGENT_MODEL=claude-haiku-4-5-20251001`), restart
4. **Docker daemon died**: `open -a Docker`, wait for whale, then `make up && make dev`
5. **Postgres ran out of disk**: `docker compose down -v` to wipe; re-init + re-seed
6. **Dashboard blank**: hard refresh (Cmd+Shift+R). Most likely SSE was disconnected during a restart.
