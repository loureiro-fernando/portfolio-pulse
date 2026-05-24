"""Eval: pension_fund persona injects the right instructions into the prompt.

We mock the Anthropic SDK and the DB. The test asserts:
1. The user message sent to the model contains the pension_fund persona block
   (mentions "capital preservation", "distributions", "risk-adjusted").
2. When the model returns a draft that itself mentions those terms, the
   skill surfaces them in the markdown_draft output.
3. The fenced JSON themes block at the end is parsed into key_themes.

This eval covers prompt-construction correctness (deterministic) and the
output-parsing path (also deterministic).
"""

import pytest
from _helpers import (  # noqa: E402  - sys.path manipulated in conftest
    load_script,
    stub_anthropic,
    stub_db_session,
)


@pytest.mark.asyncio
async def test_pension_fund_tone(monkeypatch):
    script = load_script("lp_drafter_pension")
    stub_db_session(monkeypatch, script)

    fake_draft = (
        "Dear LP,\n\n"
        "This quarter we prioritized capital preservation while delivering "
        "stable distributions and managing risk-adjusted returns across the "
        "portfolio. Burn discipline at AlphaCorp held within plan.\n\n"
        "```json\n"
        '{"key_themes": ["capital preservation", "distributions", "risk-adjusted returns"]}\n'
        "```\n"
    )
    client = stub_anthropic(monkeypatch, script, fake_draft)

    result = await script.invoke("acme", "Q1 2026", "pension_fund")

    # 1. Persona block injected
    sent_messages = client.messages.create.await_args.kwargs["messages"]
    user_msg = sent_messages[0]["content"]
    assert "capital preservation" in user_msg
    assert "distributions" in user_msg
    assert "risk-adjusted" in user_msg

    # 2. Output surfaces the terms verbatim
    assert "capital preservation" in result["markdown_draft"]
    assert "distributions" in result["markdown_draft"]

    # 3. Themes parsed
    assert result["key_themes"] == [
        "capital preservation",
        "distributions",
        "risk-adjusted returns",
    ]
    assert result["estimated_tokens"] == 2000
