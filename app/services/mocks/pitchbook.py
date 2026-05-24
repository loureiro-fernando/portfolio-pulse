"""Mock PitchBook responses. README explains how to swap for real PitchBook API."""

from typing import Any

_COMPANIES: dict[str, dict[str, Any]] = {
    "portco-1": {
        "name": "AcmeCo",
        "sector": "SaaS",
        "stage": "Series B",
        "last_valuation_usd": 180_000_000,
        "headcount": 145,
        "founded": 2019,
        "investors": ["Sequoia", "Accel", "Index Ventures"],
    },
    "portco-2": {
        "name": "BetaHealth",
        "sector": "Healthtech",
        "stage": "Series A",
        "last_valuation_usd": 65_000_000,
        "headcount": 52,
        "founded": 2021,
        "investors": ["a16z", "GV"],
    },
    "portco-3": {
        "name": "GammaFin",
        "sector": "Fintech",
        "stage": "Series C",
        "last_valuation_usd": 420_000_000,
        "headcount": 310,
        "founded": 2017,
        "investors": ["Tiger Global", "Insight Partners", "Goldman Sachs"],
    },
}

_PEERS: dict[str, list[dict[str, Any]]] = {
    "SaaS": [
        {"name": "Peer SaaS Alpha", "revenue_growth_yoy_pct": 32, "burn_multiple": 1.8},
        {"name": "Peer SaaS Beta", "revenue_growth_yoy_pct": 28, "burn_multiple": 2.1},
        {"name": "Peer SaaS Gamma", "revenue_growth_yoy_pct": 41, "burn_multiple": 1.5},
    ],
    "Healthtech": [
        {"name": "Peer Health Alpha", "revenue_growth_yoy_pct": 18, "burn_multiple": 2.8},
        {"name": "Peer Health Beta", "revenue_growth_yoy_pct": 22, "burn_multiple": 2.4},
    ],
    "Fintech": [
        {"name": "Peer Fin Alpha", "revenue_growth_yoy_pct": 25, "burn_multiple": 2.0},
        {"name": "Peer Fin Beta", "revenue_growth_yoy_pct": 30, "burn_multiple": 1.7},
        {"name": "Peer Fin Gamma", "revenue_growth_yoy_pct": 19, "burn_multiple": 2.3},
    ],
}


def fetch_company_data(portco_id: str) -> dict[str, Any]:
    """Return company data for a portco. Returns empty dict if unknown."""
    return _COMPANIES.get(portco_id, {})


def get_peer_set(sector: str) -> list[dict[str, Any]]:
    """Return peers in the same sector."""
    return _PEERS.get(sector, [])
