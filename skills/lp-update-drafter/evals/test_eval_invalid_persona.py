"""Eval: unknown persona must raise ValueError before any DB or API call.

Pass criteria:
- ValueError raised mentioning the bad persona
- _gather_context is NOT called (no DB hit)
- AsyncAnthropic is NOT instantiated
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from _helpers import load_script


@pytest.mark.asyncio
async def test_invalid_persona_rejected(monkeypatch):
    script = load_script("lp_drafter_invalid_persona")

    gather_mock = AsyncMock(return_value={})
    anthropic_mock = MagicMock()
    session_mock = MagicMock()
    monkeypatch.setattr(script, "_gather_context", gather_mock)
    monkeypatch.setattr(script, "AsyncAnthropic", anthropic_mock)
    monkeypatch.setattr(script, "SessionLocal", session_mock)

    with pytest.raises(ValueError, match="hedge_fund"):
        await script.invoke("acme", "Q1 2026", "hedge_fund")

    gather_mock.assert_not_called()
    anthropic_mock.assert_not_called()
    session_mock.assert_not_called()
