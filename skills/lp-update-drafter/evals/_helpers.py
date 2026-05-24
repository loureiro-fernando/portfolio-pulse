"""Shared loaders + mocks for lp-update-drafter evals.

The script.py uses (a) AsyncAnthropic for the Messages API and (b) SessionLocal
for the DB. We mock both at the module level (not the import path) so the
tests are hermetic and never touch network or Postgres.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock


def load_script(module_name: str):
    """Load skills/lp-update-drafter/script.py as a fresh module per test."""
    path = Path(__file__).resolve().parents[1] / "script.py"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stub_db_session(monkeypatch, script, tenant_name: str = "Acme Capital"):
    """Patch script.SessionLocal so _gather_context returns a minimal context."""
    tenant = SimpleNamespace(id="tenant-acme", slug="acme", name=tenant_name)
    portcos = [
        SimpleNamespace(id="portco-1", name="AlphaCorp", sector="fintech"),
        SimpleNamespace(id="portco-2", name="BetaHealth", sector="health"),
    ]
    alerts = [
        SimpleNamespace(
            portco_id="portco-1",
            severity="attention",
            summary="Burn elevated",
            requires_human=False,
        )
    ]
    runs: list = []

    def make_session():
        session = MagicMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)

        results = iter(
            [
                _result(tenant, scalar=True),
                _result(portcos, scalar=False),
                _result(alerts, scalar=False),
                _result(runs, scalar=False),
            ]
        )
        session.execute = AsyncMock(side_effect=lambda *_a, **_k: next(results))
        return session

    monkeypatch.setattr(script, "SessionLocal", lambda: make_session())


def _result(rows, scalar: bool):
    result = MagicMock()
    if scalar:
        result.scalar_one_or_none = MagicMock(return_value=rows)
    else:
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=rows)
        result.scalars = MagicMock(return_value=scalars)
    return result


def stub_anthropic(
    monkeypatch,
    script,
    draft_text: str,
    in_tokens: int = 1200,
    out_tokens: int = 800,
):
    """Patch script.AsyncAnthropic so messages.create returns a canned response."""
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text=draft_text)],
        usage=SimpleNamespace(input_tokens=in_tokens, output_tokens=out_tokens),
    )

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)

    monkeypatch.setattr(script, "AsyncAnthropic", MagicMock(return_value=client))
    return client
