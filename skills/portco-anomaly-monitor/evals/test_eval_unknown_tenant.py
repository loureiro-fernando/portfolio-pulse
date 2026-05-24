"""Eval: unknown tenant_slug must raise ValueError, before run_pipeline runs.

The skill resolves tenant_slug -> tenant_id by querying the Tenant table.
If the slug is missing, we abort early with a ValueError; we do NOT silently
default to a random tenant.

Pass criteria:
- ValueError raised mentioning the bad slug
- run_pipeline NOT called
- DB was queried once (for the tenant lookup)
"""

import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _load_script():
    path = Path(__file__).resolve().parents[1] / "script.py"
    spec = importlib.util.spec_from_file_location("portco_anomaly_script_unknown", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_unknown_tenant_rejected(monkeypatch):
    script = _load_script()

    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)  # tenant missing
    session.execute = AsyncMock(return_value=result)

    monkeypatch.setattr(script, "SessionLocal", lambda: session)

    pipeline_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(script, "run_pipeline", pipeline_mock)

    with pytest.raises(ValueError, match="ghost"):
        await script.invoke(
            tenant_slug="ghost",
            portco_id="portco-1",
            metric="revenue",
            value=3.0,
            period="2026-04",
        )

    pipeline_mock.assert_not_called()
    session.execute.assert_awaited_once()
