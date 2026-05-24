"""Mock Egnyte responses. README explains how to swap for real Egnyte API."""

from typing import Any

_DOCS: dict[str, dict[str, Any]] = {
    "doc-001": {
        "filename": "Q4_2025_board_deck.pdf",
        "portco_id": "portco-1",
        "category": "board_materials",
        "updated_at": "2026-01-15",
        "content": (
            "Q4 2025 Board Update - AcmeCo\n"
            "Revenue: $4.2M (vs target $4.5M, miss 7%)\n"
            "Churn ticked up to 3.1% (target 2.5%) due to two enterprise losses.\n"
            "Pipeline rebuild in progress. CEO confident in Q1 recovery.\n"
        ),
    },
    "doc-002": {
        "filename": "Layoff_announcement_internal.docx",
        "portco_id": "portco-1",
        "category": "hr",
        "updated_at": "2026-02-08",
        "content": (
            "Internal memo: 12% RIF announced today. Engineering -8 heads, "
            "Sales -5 heads. Severance: 2 months. CEO town hall Friday."
        ),
    },
    "doc-003": {
        "filename": "Q4_2025_financials_betahealth.xlsx",
        "portco_id": "portco-2",
        "category": "financials",
        "updated_at": "2026-01-20",
        "content": (
            "BetaHealth Q4 2025: ARR $8.1M (+22% QoQ). Gross margin 78%. "
            "Operating loss narrowed to $1.2M. Cash $14M, runway ~14 months at current burn."
        ),
    },
    "doc-004": {
        "filename": "FDA_510k_clearance_letter.pdf",
        "portco_id": "portco-2",
        "category": "regulatory",
        "updated_at": "2026-02-01",
        "content": (
            "FDA 510(k) clearance granted for diagnostic device. "
            "Expected to unlock $3M ARR in 6-9 months."
        ),
    },
    "doc-005": {
        "filename": "Series_C_term_sheet_gammafin.pdf",
        "portco_id": "portco-3",
        "category": "fundraising",
        "updated_at": "2026-02-12",
        "content": (
            "Series C term sheet from Tiger Global: $80M at $480M pre-money. "
            "Closing target end of March. Pro-rata for existing investors."
        ),
    },
}


def search_docs(query: str, portco_id: str | None = None) -> list[dict[str, Any]]:
    """Naive substring search across filename + content. Optional filter by portco_id."""
    query_lower = query.lower()
    results = []
    for doc_id, doc in _DOCS.items():
        if portco_id and doc["portco_id"] != portco_id:
            continue
        haystack = f"{doc['filename']} {doc['content']}".lower()
        if query_lower in haystack:
            results.append({"doc_id": doc_id, **{k: v for k, v in doc.items() if k != "content"}})
    return results


def get_doc_content(doc_id: str) -> dict[str, Any]:
    """Return full doc including content. Empty dict if not found."""
    doc = _DOCS.get(doc_id)
    if doc is None:
        return {}
    return {"doc_id": doc_id, **doc}
