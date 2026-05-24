# portco-anomaly-monitor - Human Operator Guide

## When to use manually
Run this skill outside the automatic webhook flow when you want to:
- Re-process a KPI snapshot after fixing a bug in the pipeline
- Backfill alerts for a portco that was added late to a tenant
- Smoke-test the multi-agent pipeline against a known anomaly

Do NOT use it for forward-looking projections or ad-hoc questions. For those,
talk to the LLM directly.

## How to invoke

```bash
# CLI (uses .env for ANTHROPIC_API_KEY + DATABASE_URL)
python skills/portco-anomaly-monitor/script.py \
  --tenant acme \
  --portco portco-1 \
  --metric revenue \
  --value 3.1 \
  --period 2026-04
```

Output is JSON to stdout with `alert_id`, `severity`, `requires_human`, `summary`.

## Interpreting severity
- `info` - logged only, no action required
- `attention` - posted to Slack #portfolio-pulse, GP should glance at the trend
- `urgent` - posted to Slack with @here, GP should respond within the day
- `none` - the AnomalyDetector decided the value is within expected range; no alert created

When `requires_human=true`, open a ticket in your tracker (Linear, Jira) and
assign the deal lead. The summary field is safe to paste directly.

## Troubleshooting
- `FileNotFoundError: .agents_config.json` -> run `python -m app.agents.setup`
- `unknown tenant_slug` -> run `python -m app.scripts.seed` or check the slug
- Pipeline hangs after `pipeline_started` event -> check Jaeger for the OTel
  trace; usually a tool call (Slack/Egnyte mock) is timing out
- Alert created but Slack message missing -> check `SLACK_BOT_TOKEN` env var
  and that the bot is in `#portfolio-pulse`

## Links
- Pipeline code: `app/agents/orchestrator.py`
- Agent prompts: `app/agents/prompts.py`
- Custom tools: `app/agents/tools.py`
- SSE event bus: `app/event_bus.py`

## Running the evals
The evals are deterministic - they mock `run_pipeline` and the DB, so they
never hit the Anthropic API.

```bash
pytest skills/portco-anomaly-monitor/evals -v
```

They are intentionally excluded from the default `pytest` run (pyproject
sets `testpaths=["tests"]`).
