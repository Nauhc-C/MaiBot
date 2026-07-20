from typing import Any, Iterable

import pytest

from src.chat.replyer.maisaka_generator_base import (
    REPLYER_MAX_HOOK_RETRIES,
    BaseMaisakaReplyGenerator,
    is_standalone_media_placeholder,
)
from src.common.data_models.llm_service_data_models import LLMResponseResult


class PassthroughRuntimeManager:
    async def invoke_hook(self, _hook_name: str, **_kwargs: Any) -> Any:
        return type("HookResult", (), {"kwargs": {}})()


def build_generator(responses: Iterable[str]) -> tuple[BaseMaisakaReplyGenerator, list[list[Any]]]:
    response_iterator = iter(responses)
    requests: list[list[Any]] = []

    class SequencedLLMClient:
        def __init__(self, **_: Any) -> None:
            self.task_name = "replyer"

        async def generate_response_with_messages(self, message_factory, options) -> LLMResponseResult:
            del options
            requests.append(await message_factory(self))
            return LLMResponseResult(
                response=next(response_iterator),
                model_name="test-model",
                prompt_tokens=10,
                completion_tokens=2,
                total_tokens=12,
            )

    generator = BaseMaisakaReplyGenerator(
        llm_client_cls=SequencedLLMClient,
        load_prompt_func=lambda *_args, **_kwargs: "你是一个测试用回复器。",
        enable_visual_message=False,
        replyer_mode="text",
    )
    return generator, requests


@pytest.mark.parametrize("placeholder", ["[语音消息]", "[图片]", "[表情包]"])
@pytest.mark.asyncio
async def test_standalone_media_placeholder_triggers_regeneration(monkeypatch, placeholder: str) -> None:
    runtime_manager = PassthroughRuntimeManager()
    monkeypatch.setattr(
        BaseMaisakaReplyGenerator,
        "_get_runtime_manager",
        staticmethod(lambda: runtime_manager),
    )
    generator, requests = build_generator([placeholder, "主人，早上好呀~"])

    success, result = await generator.generate_reply_with_context(
        stream_id="test-session",
        chat_history=[],
    )

    assert success is True
    assert result.completion.response_text == "主人，早上好呀~"
    assert len(requests) == 2
    assert result.metrics.extra["replyer_retry_count"] == 1
    assert "不要输出 [语音消息]、[图片]、[表情包]" in result.metrics.extra["replyer_retry_constraints"][0]


@pytest.mark.asyncio
async def test_exhausted_media_placeholder_retries_return_failure(monkeypatch) -> None:
    runtime_manager = PassthroughRuntimeManager()
    monkeypatch.setattr(
        BaseMaisakaReplyGenerator,
        "_get_runtime_manager",
        staticmethod(lambda: runtime_manager),
    )
    attempts = REPLYER_MAX_HOOK_RETRIES + 1
    generator, requests = build_generator(["[语音消息]"] * attempts)

    success, result = await generator.generate_reply_with_context(
        stream_id="test-session",
        chat_history=[],
    )

    assert success is False
    assert result.success is False
    assert result.error_message == "回复器连续返回不可发送的媒体占位符"
    assert result.completion.response_text == "[语音消息]"
    assert len(requests) == attempts
    assert result.metrics.extra["replyer_retry_count"] == REPLYER_MAX_HOOK_RETRIES


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (" [语音消息] ", True),
        ("[语音消息，转录失败]", True),
        ("[图片，识别中.....]", True),
        ("收到[语音消息]", False),
        ("这是实际回复", False),
    ],
)
def test_is_standalone_media_placeholder(text: str, expected: bool) -> None:
    assert is_standalone_media_placeholder(text) is expected
