"""Unit tests for in-memory PitchBook and Egnyte mocks."""

from app.services.mocks import egnyte, pitchbook


class TestPitchBookMock:
    def test_known_company_returns_full_record(self):
        data = pitchbook.fetch_company_data("portco-1")
        assert data["name"] == "AcmeCo"
        assert data["sector"] == "SaaS"
        assert "Sequoia" in data["investors"]

    def test_unknown_company_returns_empty_dict(self):
        assert pitchbook.fetch_company_data("does-not-exist") == {}

    def test_peer_set_returns_sector_peers(self):
        peers = pitchbook.get_peer_set("SaaS")
        assert len(peers) == 3
        assert all("revenue_growth_yoy_pct" in p for p in peers)
        assert all("burn_multiple" in p for p in peers)

    def test_peer_set_unknown_sector_returns_empty(self):
        assert pitchbook.get_peer_set("Quantum Cryptography") == []


class TestEgnyteMock:
    def test_search_returns_matches_across_filename_and_content(self):
        results = egnyte.search_docs("layoff")
        assert len(results) == 1
        assert results[0]["doc_id"] == "doc-002"
        assert results[0]["category"] == "hr"

    def test_search_filter_by_portco_id(self):
        results = egnyte.search_docs("board", portco_id="portco-1")
        assert len(results) == 1
        assert results[0]["portco_id"] == "portco-1"

    def test_search_filter_excludes_other_portcos(self):
        results = egnyte.search_docs("layoff", portco_id="portco-2")
        assert results == []

    def test_search_no_match_returns_empty(self):
        assert egnyte.search_docs("absolutely-no-doc-mentions-this-string") == []

    def test_get_doc_content_includes_full_body(self):
        doc = egnyte.get_doc_content("doc-001")
        assert "Q4 2025 Board Update" in doc["content"]
        assert doc["filename"] == "Q4_2025_board_deck.pdf"

    def test_get_doc_content_unknown_returns_empty(self):
        assert egnyte.get_doc_content("doc-999") == {}
