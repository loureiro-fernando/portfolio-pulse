"""Eval: family_office persona injects ESG / generational / alignment terms.

Same shape as test_eval_pension_fund_tone: hermetic mocks, asserts that the
prompt sent to the model carries the persona block AND that the canned
response (which we control) carries the terms back through to the output.
"""

import pytest
from _helpers import load_script, stub_anthropic, stub_db_session


@pytest.mark.asyncio
async def test_family_office_tone(monkeypatch):
    script = load_script("lp_drafter_family")
    stub_db_session(monkeypatch, script)

    fake_draft = (
        "Dear friends,\n\n"
        "Our work this quarter stayed in alignment with the values your "
        "family has championed. ESG diligence on two new positions and a "
        "generational planning conversation with our oldest LP were the "
        "personal highlights.\n\n"
        "```json\n"
        '{"key_themes": ["alignment", "ESG", "generational planning"]}\n'
        "```\n"
    )
    client = stub_anthropic(monkeypatch, script, fake_draft)

    result = await script.invoke("acme", "Q1 2026", "family_office")

    user_msg = client.messages.create.await_args.kwargs["messages"][0]["content"]
    assert "alignment" in user_msg
    assert "ESG" in user_msg
    assert "generational" in user_msg

    assert "alignment" in result["markdown_draft"]
    assert "ESG" in result["markdown_draft"]
    assert "generational" in result["markdown_draft"]

    assert result["key_themes"] == ["alignment", "ESG", "generational planning"]
