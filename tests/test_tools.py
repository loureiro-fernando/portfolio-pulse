"""Tests for custom tool schema registry and dispatcher (no DB/Slack/Anthropic I/O)."""

import json

import pytest

from app.agents import tools


class TestToolSchemas:
    def test_all_three_agents_have_tools(self):
        assert "anomaly" in tools.TOOL_SCHEMAS
        assert "context" in tools.TOOL_SCHEMAS
        assert "severity" in tools.TOOL_SCHEMAS

    def test_each_schema_has_required_fields(self):
        for agent_tools in tools.TOOL_SCHEMAS.values():
            for tool in agent_tools:
                assert tool["type"] == "custom"
                assert "name" in tool
                assert "description" in tool
                assert "input_schema" in tool
                assert tool["input_schema"]["type"] == "object"

    def test_tool_names_are_unique_across_agents(self):
        names: list[str] = []
        for agent_tools in tools.TOOL_SCHEMAS.values():
            for tool in agent_tools:
                names.append(tool["name"])
        assert len(names) == len(set(names)), f"duplicate tool names: {names}"

    def test_all_tool_schemas_unions_correctly(self):
        union = tools.all_tool_schemas()
        flat_count = sum(len(v) for v in tools.TOOL_SCHEMAS.values())
        assert len(union) == flat_count

    def test_expected_tools_present(self):
        names = {t["name"] for ts in tools.TOOL_SCHEMAS.values() for t in ts}
        assert names == {
            "fetch_history",
            "compare_peers",
            "slack_read_recent_messages",
            "pitchbook_fetch_company_data",
            "pitchbook_get_peer_set",
            "egnyte_search_docs",
            "egnyte_get_doc_content",
            "get_tenant_policy",
        }


class TestDispatchPitchBook:
    @pytest.mark.asyncio
    async def test_pitchbook_fetch_company_data_returns_json(self):
        raw = await tools.dispatch("pitchbook_fetch_company_data", {"portco_id": "portco-1"})
        data = json.loads(raw)
        assert data["name"] == "AcmeCo"

    @pytest.mark.asyncio
    async def test_pitchbook_peer_set_returns_json_list(self):
        raw = await tools.dispatch("pitchbook_get_peer_set", {"sector": "SaaS"})
        data = json.loads(raw)
        assert isinstance(data, list)
        assert len(data) == 3


class TestDispatchEgnyte:
    @pytest.mark.asyncio
    async def test_egnyte_search_docs_returns_json_list(self):
        raw = await tools.dispatch("egnyte_search_docs", {"query": "board"})
        data = json.loads(raw)
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_egnyte_search_with_portco_filter(self):
        raw = await tools.dispatch(
            "egnyte_search_docs",
            {"query": "board", "portco_id": "portco-1"},
        )
        data = json.loads(raw)
        assert all(d["portco_id"] == "portco-1" for d in data)

    @pytest.mark.asyncio
    async def test_egnyte_get_doc_content_returns_json(self):
        raw = await tools.dispatch("egnyte_get_doc_content", {"doc_id": "doc-001"})
        data = json.loads(raw)
        assert "content" in data
        assert "Q4 2025" in data["content"]


class TestDispatchPolicy:
    @pytest.mark.asyncio
    async def test_get_tenant_policy_returns_json(self):
        raw = await tools.dispatch("get_tenant_policy", {"tenant_slug": "acme"})
        data = json.loads(raw)
        assert data["human_handoff_severity"] == "urgent"


class TestDispatchErrors:
    @pytest.mark.asyncio
    async def test_unknown_tool_raises_value_error(self):
        with pytest.raises(ValueError, match="unknown tool"):
            await tools.dispatch("totally_made_up_tool", {})


class TestSeverityEmoji:
    def test_all_severities_have_emoji(self):
        for severity in ["info", "attention", "urgent"]:
            assert severity in tools.SEVERITY_EMOJI
            assert tools.SEVERITY_EMOJI[severity].startswith(":")
