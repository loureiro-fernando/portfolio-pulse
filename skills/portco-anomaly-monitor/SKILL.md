---
name: portco-anomaly-monitor
description: Trigger this skill when a portfolio company KPI (revenue, burn, churn_pct) arrives and you need to (1) detect if it's anomalous vs history and peer set, (2) gather context from internal docs and Slack, (3) classify severity per tenant policy, and (4) post a structured alert. Use when a user mentions a portco KPI drop/spike, says "investigate portco X", or asks for a portfolio health check. Do NOT trigger for forward-looking projections or pure reporting - only for actual incoming KPI events.
version: 0.1.0
---

# portco-anomaly-monitor

Multi-tenant pipeline that detects, contextualizes, and classifies portfolio company KPI anomalies.

## When to use
Trigger on incoming KPI events for portfolio companies. Example phrasings: "portco-1 just reported $3.1M revenue for April", "investigate the burn spike at GammaFin", "is BetaHealth's churn normal?".

## Inputs (required)
- tenant_slug (string) - e.g. "acme"
- portco_id (string) - e.g. "portco-1"
- metric (string) - one of: revenue, burn, churn_pct
- value (float) - latest value
- period (string) - YYYY-MM

## What it does
1. AnomalyDetector compares value vs 12-month history + sector peer average
2. ContextBuilder enriches with PitchBook + Egnyte docs + Slack
3. SeverityClassifier applies tenant policy -> JSON verdict
4. Posts to Slack #portfolio-pulse if severity >= attention
5. Persists AgentRun + Alert in Postgres
6. Streams events to `/stream/{tenant_slug}` SSE

## Outputs
- `alert_id` (int) of created Alert
- `severity` (info | attention | urgent)
- `requires_human` (bool)
- `summary` (string)

## Cost
~$0.06 per invocation with Haiku 4.5.

## See also
- `script.py` for programmatic invocation
- `instructions.md` for human operator workflow
- `evals/` for 5 deterministic test cases
