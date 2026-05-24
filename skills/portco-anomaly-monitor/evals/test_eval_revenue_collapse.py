"""Eval: revenue collapse should surface as an urgent alert requiring human action.

Scenario: portco-1 (sector=fintech) reports $3.1M revenue for 2026-04, a 31%
drop vs the trailing 12 months. The orchestrator's SeverityClassifier should
produce severity=urgent, requires_human=true, and the skill's invoke() should
return those fields verbatim from the persisted Alert row.

Pass criteria:
- invoke() returns dict with severity=='urgent'
- requires_human is True
- alert_id is the integer PK of the mocked Alert
- run_pipeline was called exactly once with the right args
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "script.py"
    spec = importlib.util.spec_from_file_location("portco_anomaly_script", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_revenue_collapse_urgent(monkeypatch):
    script = _load_script()

    tenant_row = SimpleNamespace(id="tenant-acme", slug="acme")
    alert_row = SimpleNamespace(
        id=42,
        severity="urgent",
        summary="Revenue dropped 31% MoM; deal lead must respond today.",
        requires_human=True,
    )

    # Two consecutive SessionLocal() context managers: one for tenant lookup,
    # one for alert lookup. Each yields a session whose execute() returns a
    # scalar_one_or_none() with the right row.
    def make_session(row):
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=row)
        session.execute = AsyncMock(return_value=result)
        return session

    sessions = iter([make_session(tenant_row), make_session(alert_row)])
    monkeypatch.setattr(script, "SessionLocal", lambda: next(sessions))

    pipeline_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(script, "run_pipeline", pipeline_mock)

    result = await script.invoke(
        tenant_slug="acme",
        portco_id="portco-1",
        metric="revenue",
        value=3.1,
        period="2026-04",
    )

    assert result == {
        "alert_id": 42,
        "severity": "urgent",
        "requires_human": True,
        "summary": "Revenue dropped 31% MoM; deal lead must respond today.",
    }
    pipeline_mock.assert_awaited_once_with(
        "acme", "tenant-acme", "portco-1", "revenue", 3.1, "2026-04"
    )
