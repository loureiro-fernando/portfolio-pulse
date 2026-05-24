"""Tenant policies for severity classification.

Hardcoded for MVP. In production these would live in a `tenant_policies` table
or a config service. The structure stays the same - only the source changes.
"""

from typing import Any

_POLICIES: dict[str, dict[str, Any]] = {
    "acme": {
        "revenue_drop_pct": {"attention": 10, "urgent": 25},
        "burn_increase_pct": {"attention": 15, "urgent": 40},
        "churn_increase_pct": {"attention": 5, "urgent": 15},
        "human_handoff_severity": "urgent",
        "notify_channels": ["slack:#portfolio-pulse"],
    },
}

_DEFAULT_POLICY: dict[str, Any] = {
    "revenue_drop_pct": {"attention": 15, "urgent": 30},
    "burn_increase_pct": {"attention": 20, "urgent": 50},
    "churn_increase_pct": {"attention": 10, "urgent": 20},
    "human_handoff_severity": "urgent",
    "notify_channels": ["slack:#portfolio-pulse"],
}


def get_tenant_policy(tenant_slug: str) -> dict[str, Any]:
    """Return policy for tenant_slug. Falls back to default."""
    return _POLICIES.get(tenant_slug, _DEFAULT_POLICY)
