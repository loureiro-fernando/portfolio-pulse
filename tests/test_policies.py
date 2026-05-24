"""Unit tests for tenant policy lookup."""

from app.services.policies import get_tenant_policy


def test_known_tenant_returns_specific_policy():
    policy = get_tenant_policy("acme")
    assert policy["revenue_drop_pct"]["urgent"] == 25
    assert policy["human_handoff_severity"] == "urgent"
    assert "slack:#portfolio-pulse" in policy["notify_channels"]


def test_unknown_tenant_falls_back_to_default():
    policy = get_tenant_policy("does-not-exist")
    assert policy["revenue_drop_pct"]["attention"] == 15
    assert policy["revenue_drop_pct"]["urgent"] == 30
    assert policy["human_handoff_severity"] == "urgent"


def test_all_thresholds_have_attention_and_urgent():
    for tenant_slug in ["acme", "any-unknown-tenant"]:
        policy = get_tenant_policy(tenant_slug)
        for metric in ["revenue_drop_pct", "burn_increase_pct", "churn_increase_pct"]:
            assert "attention" in policy[metric]
            assert "urgent" in policy[metric]
            assert policy[metric]["attention"] < policy[metric]["urgent"]
