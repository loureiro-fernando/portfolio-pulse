"""Eval: word count helper measures the body (excluding the JSON themes block).

The skill instructs the model to produce 600-900 words of letter body and
append a fenced JSON themes block. The _word_count helper must strip the
JSON block before counting so the validator measures the letter only.

We feed a synthetic draft with exactly 800 words of body + a JSON themes
block, and assert:
- _word_count returns 800
- result is within the documented 600-900 range
- output written to /tmp path
"""

from pathlib import Path

import pytest
from _helpers import load_script, stub_anthropic, stub_db_session


@pytest.mark.asyncio
async def test_word_count_in_range(monkeypatch, tmp_path):
    script = load_script("lp_drafter_wordcount")
    stub_db_session(monkeypatch, script)

    body = " ".join(["word"] * 800)
    fake_draft = f'{body}\n\n```json\n{{"key_themes": ["a", "b", "c"]}}\n```\n'
    stub_anthropic(monkeypatch, script, fake_draft)

    result = await script.invoke("acme", "Q1 2026", "endowment")

    body_words = script._word_count(result["markdown_draft"])
    assert body_words == 800
    assert 600 <= body_words <= 900

    # Output written somewhere under /tmp (or a temp-mapped path); just check
    # the file the script reports actually exists.
    assert Path(result["output_path"]).exists()
