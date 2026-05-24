"""Eval: endowment persona injects IRR / long-term / co-invest terms."""

import pytest
from _helpers import load_script, stub_anthropic, stub_db_session


@pytest.mark.asyncio
async def test_endowment_tone(monkeypatch):
    script = load_script("lp_drafter_endow")
    stub_db_session(monkeypatch, script)

    fake_draft = (
        "Dear CIO,\n\n"
        "Long-term IRR remains the lens we use to evaluate the portfolio. "
        "Vintage diversification and a co-invest pipeline of two later-stage "
        "names should support sustained returns through the J-curve.\n\n"
        "```json\n"
        '{"key_themes": ["long-term IRR", "co-invest pipeline", "J-curve management"]}\n'
        "```\n"
    )
    client = stub_anthropic(monkeypatch, script, fake_draft)

    result = await script.invoke("acme", "Q1 2026", "endowment")

    user_msg = client.messages.create.await_args.kwargs["messages"][0]["content"]
    assert "IRR" in user_msg
    assert "long-term" in user_msg
    assert "co-invest" in user_msg.lower()

    assert "IRR" in result["markdown_draft"]
    assert "long-term" in result["markdown_draft"].lower()
    assert "co-invest" in result["markdown_draft"].lower()

    assert "long-term IRR" in result["key_themes"]
    assert "co-invest pipeline" in result["key_themes"]
