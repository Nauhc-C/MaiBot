import sys
import types
from types import SimpleNamespace

import pytest

rapidfuzz_module = types.ModuleType("rapidfuzz")
rapidfuzz_distance_module = types.ModuleType("rapidfuzz.distance")
rapidfuzz_distance_module.Levenshtein = SimpleNamespace(distance=lambda *_args, **_kwargs: 0)
rapidfuzz_module.distance = rapidfuzz_distance_module
sys.modules.setdefault("rapidfuzz", rapidfuzz_module)
sys.modules.setdefault("rapidfuzz.distance", rapidfuzz_distance_module)

from src.maisaka import reasoning_engine as reasoning_engine_module
from src.maisaka.reasoning_engine import MaisakaReasoningEngine


@pytest.mark.asyncio
async def test_run_timing_gate_treats_text_without_tool_calls_as_continue(monkeypatch) -> None:
    """Timing Gate 只返回判断文本但没有工具调用时，应继续进入 Planner。"""

    engine = object.__new__(MaisakaReasoningEngine)
    stop_state = {"entered": False}
    invalid_hint_calls = {"count": 0}

    engine._runtime = SimpleNamespace(
        _force_next_timing_continue=False,
        _chat_history=[],
        log_prefix="[test]",
        _enter_stop_state=lambda: stop_state.__setitem__("entered", True),
    )
    engine._build_tool_availability_context = lambda: None
    engine._build_timing_gate_system_prompt = lambda: "timing-gate"

    async def fake_run_timing_gate_sub_agent(*, system_prompt: str, tool_definitions: list[dict]) -> SimpleNamespace:
        assert system_prompt == "timing-gate"
        assert tool_definitions == [{"name": "continue"}, {"name": "no_action"}, {"name": "wait"}]
        return SimpleNamespace(tool_calls=[], content="先做节奏分析")

    engine._run_timing_gate_sub_agent = fake_run_timing_gate_sub_agent
    engine._append_timing_gate_invalid_tool_hint = lambda invalid_tool_text: invalid_hint_calls.__setitem__("count", 1)

    monkeypatch.setattr(
        reasoning_engine_module,
        "get_timing_tools",
        lambda _context: [{"name": "continue"}, {"name": "no_action"}, {"name": "wait"}],
    )

    action, response, summaries, monitor_results = await engine._run_timing_gate(SimpleNamespace())

    assert action == "continue"
    assert response.content == "先做节奏分析"
    assert summaries == ["- continue [缺少 Timing 工具]: 未返回控制工具调用但返回了判断内容，已继续进入 Planner"]
    assert monitor_results == []
    assert stop_state["entered"] is False
    assert invalid_hint_calls["count"] == 0


@pytest.mark.asyncio
async def test_run_timing_gate_downgrades_empty_missing_tool_calls_to_no_action(monkeypatch) -> None:
    """Timing Gate 没有文本也没有工具调用时，仍按 no_action 结束。"""

    engine = object.__new__(MaisakaReasoningEngine)
    stop_state = {"entered": False}
    invalid_hint_calls = {"count": 0}

    engine._runtime = SimpleNamespace(
        _force_next_timing_continue=False,
        _chat_history=[],
        log_prefix="[test]",
        _enter_stop_state=lambda: stop_state.__setitem__("entered", True),
    )
    engine._build_tool_availability_context = lambda: None
    engine._build_timing_gate_system_prompt = lambda: "timing-gate"

    async def fake_run_timing_gate_sub_agent(*, system_prompt: str, tool_definitions: list[dict]) -> SimpleNamespace:
        assert system_prompt == "timing-gate"
        assert tool_definitions == [{"name": "continue"}, {"name": "no_action"}, {"name": "wait"}]
        return SimpleNamespace(tool_calls=[], content="")

    engine._run_timing_gate_sub_agent = fake_run_timing_gate_sub_agent
    engine._append_timing_gate_invalid_tool_hint = lambda invalid_tool_text: invalid_hint_calls.__setitem__("count", 1)

    monkeypatch.setattr(
        reasoning_engine_module,
        "get_timing_tools",
        lambda _context: [{"name": "continue"}, {"name": "no_action"}, {"name": "wait"}],
    )

    action, response, summaries, monitor_results = await engine._run_timing_gate(SimpleNamespace())

    assert action == "no_action"
    assert response.content == ""
    assert summaries == ["- no_action [缺少 Timing 工具]: 未返回任何控制工具调用，已停止本轮并等待新消息"]
    assert monitor_results == []
    assert stop_state["entered"] is True
    assert invalid_hint_calls["count"] == 0
