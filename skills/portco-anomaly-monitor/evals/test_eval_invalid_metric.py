"""Eval: invalid metric must fail fast with ValueError, before any I/O.

The skill contract restricts `metric` to revenue|burn|churn_pct. Any other
value must raise ValueError synchronously, without touching the DB or the
Anthropic API.

Pass criteria:
- ValueError raised
- Error message includes the offending metric name
- run_pipeline is NOT called
- SessionLocal is NOT called
"""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "script.py"
    spec = importlib.util.spec_from_file_location("portco_anomaly_script_invalid", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_invalid_metric_rejected(monkeypatch):
    script = _load_script()

    pipeline_mock = AsyncMock(return_value=None)
    session_mock = MagicMock()
    monkeypatch.setattr(script, "run_pipeline", pipeline_mock)
    monkeypatch.setattr(script, "SessionLocal", session_mock)

    with pytest.raises(ValueError, match="foo"):
        await script.invoke(
            tenant_slug="acme",
            portco_id="portco-1",
            metric="foo",
            value=1.0,
            period="2026-04",
        )

    pipeline_mock.assert_not_called()
    session_mock.assert_not_called()
