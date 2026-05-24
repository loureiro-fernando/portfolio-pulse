# lp-update-drafter - Human Operator Guide

## When to use
End of quarter. The GP needs a starting draft of the LP letter, tailored to a
specific audience segment, that pulls real portfolio data instead of starting
from a blank page. The draft is a starting point, not a final letter - always
have the GP review.

Do NOT use this for:
- Individual portco alerts (use portco-anomaly-monitor instead)
- Ad-hoc LP questions (talk to the LLM directly with the LP's email in context)
- Marketing material (LP letters are private and stylistically different)

## How to invoke

```bash
python skills/lp-update-drafter/script.py \
  --tenant acme \
  --period "Q1 2026" \
  --persona pension_fund
```

The script writes the markdown draft to
`/tmp/lp_update_{tenant}_{period}_{persona}.md` and prints a JSON summary
(themes, token count, word count, output path) to stdout.

## Personas
- `pension_fund` - conservative, fiduciary, focused on cash distributions
- `family_office` - relational, ESG-aware, generational
- `endowment` - analytical, long-horizon, co-invest interested

If you don't know the audience, default to `endowment` - it's the most
neutral analytically.

## Troubleshooting
- `unknown tenant_slug` -> check `app/scripts/seed.py` ran for this tenant
- Draft is too short / too long -> the model is asked for 600-900 words; if
  it drifts, re-run; if it keeps drifting, edit the SYSTEM_PROMPT in script.py
- Missing JSON themes block -> the model occasionally skips the fenced JSON;
  the extractor returns an empty list rather than crashing

## Running the evals
Evals are deterministic: they mock the Anthropic SDK and the DB so no real
API calls happen.

```bash
pytest skills/lp-update-drafter/evals -v
```

They are excluded from the default `pytest` run (pyproject sets
`testpaths=["tests"]`).
