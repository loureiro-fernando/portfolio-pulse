---
name: lp-update-drafter
description: Trigger this skill when a GP needs to draft a quarterly portfolio update letter to send to LPs. Accepts a tenant_slug, a target period (e.g. "Q1 2026"), and an audience persona (pension_fund | family_office | endowment). Produces a markdown draft of 600-900 words covering portfolio highlights, top performers, watchlist items, capital activity, and a forward outlook tailored to the persona's typical concerns. Do NOT trigger for individual portco alerts (use portco-anomaly-monitor) or for ad-hoc LP questions (use direct chat).
version: 0.1.0
---

# lp-update-drafter

Generate quarterly LP update letter draft. Three personas with distinct concerns:
- pension_fund: capital preservation, cash distributions, risk-adjusted returns
- family_office: tax efficiency, alignment with family values/ESG, generational planning
- endowment: long-term IRR, J-curve management, co-investment opportunities

## Inputs
- tenant_slug (string)
- period (string) - e.g. "Q1 2026"
- persona (pension_fund | family_office | endowment)

## Outputs
- markdown_draft (string) - 600-900 word letter
- key_themes (list of strings) - 3-5 themes emphasized
- estimated_tokens (int)

## Cost
~$0.02 per draft with Haiku 4.5.
