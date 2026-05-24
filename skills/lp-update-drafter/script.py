"""Generate an LP quarterly update letter draft, persona-aware.

Design decision: uses the Messages API (`client.messages.create`) directly
rather than the Managed Agents stack used by portco-anomaly-monitor.
Rationale:
- This is a one-shot generation, not a multi-step tool-using workflow.
- No need for a coordinator + specialists.
- No need to persist an Environment + Agent in .agents_config.json.
- Cheaper and faster: single round-trip with Haiku 4.5.

The script pulls portcos + recent alerts + agent runs for the tenant/period
from Postgres, builds a context block, and feeds it to a persona-templated
system prompt. The draft is written to /tmp/lp_update_{tenant}_{period}_{persona}.md.
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy import select

from app.config import settings
from app.db import SessionLocal
from app.models.entities import AgentRun, Alert, Portco, Tenant

VALID_PERSONAS = {"pension_fund", "family_office", "endowment"}

PERSONA_INSTRUCTIONS = {
    "pension_fund": (
        "Audience: pension fund LP. Emphasize capital preservation, predictable "
        "cash distributions, risk-adjusted returns, and downside protection. "
        "Tone: measured, conservative, fiduciary. Avoid hype. Cite concrete "
        "risk-mitigation actions taken on watchlist names."
    ),
    "family_office": (
        "Audience: family office LP. Emphasize alignment with family values "
        "and ESG, tax-efficient structuring (carry, distribution timing), "
        "generational planning, and a personal voice. Tone: relational, warm, "
        "and candid about both wins and concerns."
    ),
    "endowment": (
        "Audience: endowment LP. Emphasize long-term IRR, J-curve management, "
        "vintage diversification, and co-investment opportunities. Tone: "
        "analytical, peer-to-peer with the CIO, and willing to discuss strategic "
        "shifts in the portfolio construction thesis."
    ),
}

SYSTEM_PROMPT = """You are a GP writing a quarterly LP update letter.
Produce a markdown draft of 600-900 words covering, in this order:
1. One-paragraph greeting addressing the LP segment.
2. Portfolio highlights - 2-3 specific wins this period.
3. Top performers - 1-2 portcos with concrete numbers from the context.
4. Watchlist - 1-2 portcos flagged by alerts; describe action plan.
5. Capital activity - new investments, follow-ons, exits this period.
6. Forward outlook - explicitly tailored to the audience persona below.

At the end, append a fenced JSON block with the schema:
```json
{"key_themes": ["theme1", "theme2", "theme3"]}
```
Keep the JSON to 3-5 themes. Do not include anything after the JSON block.
"""


async def _gather_context(tenant_slug: str, period: str) -> dict[str, Any]:
    async with SessionLocal() as db:
        tenant = (
            await db.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            raise ValueError(f"unknown tenant_slug: {tenant_slug}")

        portcos = (
            (await db.execute(select(Portco).where(Portco.tenant_id == tenant.id))).scalars().all()
        )
        alerts = (
            (
                await db.execute(
                    select(Alert)
                    .where(Alert.tenant_id == tenant.id)
                    .order_by(Alert.id.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )
        runs = (
            (
                await db.execute(
                    select(AgentRun)
                    .where(AgentRun.tenant_id == tenant.id)
                    .order_by(AgentRun.id.desc())
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )

    return {
        "tenant_name": tenant.name,
        "period": period,
        "portcos": [{"id": p.id, "name": p.name, "sector": p.sector} for p in portcos],
        "alerts": [
            {
                "portco_id": a.portco_id,
                "severity": a.severity,
                "summary": a.summary,
                "requires_human": a.requires_human,
            }
            for a in alerts
        ],
        "agent_run_count": len(runs),
    }


def _render_user_message(context: dict[str, Any], persona: str) -> str:
    persona_block = PERSONA_INSTRUCTIONS[persona]
    return (
        f"Period: {context['period']}\n"
        f"Fund: {context['tenant_name']}\n"
        f"Portfolio companies ({len(context['portcos'])}):\n"
        f"{json.dumps(context['portcos'], indent=2)}\n\n"
        f"Recent alerts (most recent first):\n"
        f"{json.dumps(context['alerts'], indent=2)}\n\n"
        f"Agent monitoring runs this quarter: {context['agent_run_count']}\n\n"
        f"PERSONA INSTRUCTIONS:\n{persona_block}\n\n"
        f"Write the draft now."
    )


_THEMES_RE = re.compile(r"```json\s*(\{[\s\S]*?\})\s*```", re.MULTILINE)


def _extract_themes(text: str) -> list[str]:
    match = _THEMES_RE.search(text)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    themes = data.get("key_themes", [])
    return [str(t) for t in themes if isinstance(t, str)][:5]


def _word_count(text: str) -> int:
    body = _THEMES_RE.sub("", text)
    return len(body.split())


async def invoke(tenant_slug: str, period: str, persona: str) -> dict[str, Any]:
    if persona not in VALID_PERSONAS:
        raise ValueError(f"persona must be one of {sorted(VALID_PERSONAS)}, got {persona!r}")

    context = await _gather_context(tenant_slug, period)

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_message = _render_user_message(context, persona)

    response = await client.messages.create(
        model=settings.agent_model,
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    text_parts = [
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ]
    draft = "".join(text_parts)

    out_path = Path(f"/tmp/lp_update_{tenant_slug}_{period.replace(' ', '_')}_{persona}.md")
    out_path.write_text(draft)

    usage = getattr(response, "usage", None)
    estimated_tokens = 0
    if usage is not None:
        estimated_tokens = int(
            getattr(usage, "input_tokens", 0) + getattr(usage, "output_tokens", 0)
        )

    return {
        "markdown_draft": draft,
        "key_themes": _extract_themes(draft),
        "estimated_tokens": estimated_tokens,
        "output_path": str(out_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Draft an LP quarterly update letter")
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--period", required=True, help='e.g. "Q1 2026"')
    parser.add_argument("--persona", required=True, choices=sorted(VALID_PERSONAS))
    args = parser.parse_args()

    result = asyncio.run(invoke(args.tenant, args.period, args.persona))
    # Print metadata (not the full draft) to stdout; draft is on disk.
    summary = {k: v for k, v in result.items() if k != "markdown_draft"}
    summary["word_count"] = _word_count(result["markdown_draft"])
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
