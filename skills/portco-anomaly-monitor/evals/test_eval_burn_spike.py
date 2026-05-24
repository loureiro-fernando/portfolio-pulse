"""Eval: a moderate burn spike should be classified as 'attention'.

Scenario: portco-3 (sector=infra) reports $9.5M burn for 2026-04 - elevated
but not catastrophic. The SeverityClassifier policy maps this to severity=
attention with requires_human=false (a single-day spike is monitored, not
escalated). The skill must surface those fields and an alert_id.

Pass criteria:
- severity == "attention"
- requires_human is False (single point - watch, don't escalate)
- alert_id is set
- summary is non-empty
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "script.py"
    spec = importlib.util.spec_from_file_location("portco_anomaly_script_burn", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_burn_spike_attention(monkeypatch):
    script = _load_script()

    tenant_row = SimpleNamespace(id="tenant-acme", slug="acme")
    alert_row = SimpleNamespace(
        id=77,
        severity="attention",
        summary="Burn elevated 18% vs trailing 3-month average; monitoring.",
        requires_human=False,
    )

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
        portco_id="portco-3",
        metric="burn",
        value=9.5,
        period="2026-04",
    )

    assert result["severity"] == "attention"
    assert result["requires_human"] is False
    assert result["alert_id"] == 77
    assert result["summary"]
