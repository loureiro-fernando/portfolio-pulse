"""Eval: a healthy revenue print should NOT produce an alert.

Scenario: portco-2 reports $3.7M revenue for 2026-04 - consistent with the
existing growth curve. The AnomalyDetector returns NORMAL, so the orchestrator
never persists an Alert row. The skill's invoke() must detect the absence of
an Alert and return a sentinel verdict with severity="none".

Pass criteria:
- alert_id is None
- severity == "none"
- requires_human is False
- summary mentions "no anomaly"
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "script.py"
    spec = importlib.util.spec_from_file_location("portco_anomaly_script_normal", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_normal_growth_no_alert(monkeypatch):
    script = _load_script()

    tenant_row = SimpleNamespace(id="tenant-acme", slug="acme")

    def make_session(row):
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=row)
        session.execute = AsyncMock(return_value=result)
        return session

    # 1st session: tenant exists. 2nd session: no Alert row found.
    sessions = iter([make_session(tenant_row), make_session(None)])
    monkeypatch.setattr(script, "SessionLocal", lambda: next(sessions))

    pipeline_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(script, "run_pipeline", pipeline_mock)

    result = await script.invoke(
        tenant_slug="acme",
        portco_id="portco-2",
        metric="revenue",
        value=3.7,
        period="2026-04",
    )

    assert result["alert_id"] is None
    assert result["severity"] == "none"
    assert result["requires_human"] is False
    assert "no anomaly" in result["summary"].lower()
    pipeline_mock.assert_awaited_once()
