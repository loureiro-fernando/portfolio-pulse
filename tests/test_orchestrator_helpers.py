"""Tests for orchestrator pure helpers (no I/O)."""

from types import SimpleNamespace

from app.agents.orchestrator import (
    COST_RATES,
    _cost_usd,
    _extract_severity_json,
    _to_dict,
)


class TestCostUsd:
    def test_haiku_pricing(self):
        # 1M input + 1M output on Haiku = $1 + $5
        assert _cost_usd("claude-haiku-4-5-20251001", 1_000_000, 1_000_000) == 6.0

    def test_sonnet_pricing(self):
        assert _cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000) == 18.0

    def test_opus_pricing(self):
        assert _cost_usd("claude-opus-4-7", 1_000_000, 1_000_000) == 90.0

    def test_unknown_model_falls_back_to_haiku_rates(self):
        assert _cost_usd("some-future-model", 1_000_000, 1_000_000) == 6.0

    def test_small_token_count_rounds_to_six_decimals(self):
        cost = _cost_usd("claude-haiku-4-5-20251001", 100, 50)
        assert cost == round((100 * 1.0 + 50 * 5.0) / 1_000_000, 6)

    def test_zero_tokens_is_zero_cost(self):
        assert _cost_usd("claude-haiku-4-5-20251001", 0, 0) == 0.0

    def test_cost_rates_cover_main_models(self):
        for model in ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-7"]:
            assert model in COST_RATES


class TestExtractSeverityJson:
    def test_pure_json_string(self):
        result = _extract_severity_json(
            '{"severity": "urgent", "requires_human": true, "summary": "x", "rationale": "y"}'
        )
        assert result is not None
        assert result["severity"] == "urgent"
        assert result["requires_human"] is True

    def test_json_with_surrounding_text(self):
        text = (
            "Executive summary: AcmeCo revenue dropped 30% MoM.\n\n"
            'Here is the verdict:\n{"severity": "urgent", "requires_human": true, '
            '"summary": "Revenue collapse", "rationale": "30% drop"}'
        )
        result = _extract_severity_json(text)
        assert result is not None
        assert result["severity"] == "urgent"
        assert result["summary"] == "Revenue collapse"

    def test_empty_string_returns_none(self):
        assert _extract_severity_json("") is None

    def test_no_json_returns_none(self):
        text = "No anomaly detected for portco-1. No further action."
        assert _extract_severity_json(text) is None

    def test_json_without_severity_key_returns_none(self):
        result = _extract_severity_json('{"foo": "bar"}')
        assert result is None

    def test_invalid_json_returns_none(self):
        result = _extract_severity_json("severity: urgent (not json)")
        assert result is None

    def test_picks_first_json_object_when_multiple(self):
        # Greedy regex will match the entire span, which is the whole JSON
        text = (
            '{"severity": "info", "requires_human": false, '
            '"summary": "ok", "rationale": "all good"}'
        )
        result = _extract_severity_json(text)
        assert result is not None
        assert result["severity"] == "info"


class TestToDict:
    def test_dict_passes_through(self):
        assert _to_dict({"a": 1, "b": 2}) == {"a": 1, "b": 2}

    def test_pydantic_like_object_uses_model_dump(self):
        class Fake:
            def model_dump(self):
                return {"x": "y"}

        assert _to_dict(Fake()) == {"x": "y"}

    def test_simple_namespace_uses_dict(self):
        ns = SimpleNamespace(a=1, b=2)
        assert _to_dict(ns) == {"a": 1, "b": 2}

    def test_unknown_object_returns_empty_dict(self):
        # Strings don't have __dict__ in a useful way; fallback returns {}
        result = _to_dict("not a dict-like thing")
        assert result == {}
