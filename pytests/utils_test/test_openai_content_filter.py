from types import SimpleNamespace
from typing import Any, AsyncIterator, cast

import pytest

from src.config.model_configs import ReasoningParseMode, ToolArgumentParseMode
from src.llm_models.exceptions import ContentFilterException, ModelAttemptFailed
from src.llm_models.model_client.base_client import APIResponse, ResponseRequest
from src.llm_models.model_client.openai_client import (
    _default_normal_response_parser,
    _default_stream_response_handler,
)
from src.llm_models.utils_model import LLMOrchestrator, RequestType


def test_normal_response_parser_rejects_content_filter_text() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="content_filter",
                message=SimpleNamespace(content="你好，我无法给到相关内容。"),
            )
        ],
        model="deepseek-v4-flash",
    )

    with pytest.raises(ContentFilterException) as exc_info:
        _default_normal_response_parser(
            cast(Any, response),
            reasoning_parse_mode=ReasoningParseMode.AUTO,
            tool_argument_parse_mode=ToolArgumentParseMode.AUTO,
            reasoning_key="reasoning_content",
        )

    assert exc_info.value.ext_info is response
    assert "matched_by=finish_reason" in str(exc_info.value)


def test_normal_response_parser_rejects_known_filter_text_without_finish_reason() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="你好，我无法给到相关内容。"),
            )
        ],
        model="deepseek-v4-flash",
    )

    with pytest.raises(ContentFilterException) as exc_info:
        _default_normal_response_parser(
            cast(Any, response),
            reasoning_parse_mode=ReasoningParseMode.AUTO,
            tool_argument_parse_mode=ToolArgumentParseMode.AUTO,
            reasoning_key="reasoning_content",
        )

    assert exc_info.value.ext_info is response
    assert "matched_by=response_content" in str(exc_info.value)


@pytest.mark.asyncio
async def test_stream_response_handler_rejects_content_filter_text() -> None:
    async def response_stream() -> AsyncIterator[Any]:
        yield SimpleNamespace(
            model="deepseek-v4-flash",
            usage=None,
            choices=[
                SimpleNamespace(
                    finish_reason="content_filter",
                    delta=SimpleNamespace(
                        content="你好，我无法给到相关内容。",
                        tool_calls=None,
                    ),
                )
            ],
        )

    with pytest.raises(ContentFilterException) as exc_info:
        await _default_stream_response_handler(
            cast(Any, response_stream()),
            None,
            reasoning_parse_mode=ReasoningParseMode.AUTO,
            tool_argument_parse_mode=ToolArgumentParseMode.AUTO,
            reasoning_key="reasoning_content",
        )

    assert exc_info.value.ext_info == {
        "finish_reason": "content_filter",
        "model": "deepseek-v4-flash",
    }


@pytest.mark.asyncio
async def test_content_filter_skips_same_model_without_retry() -> None:
    class FilteredClient:
        def __init__(self) -> None:
            self.calls = 0

        async def get_response(self, request: ResponseRequest) -> Any:
            del request
            self.calls += 1
            raise ContentFilterException(message="响应被上游内容审核拦截")

    provider = SimpleNamespace(max_retry=3, retry_interval=0)
    model_info = SimpleNamespace(name="freedsv4f")
    request = ResponseRequest(
        model_info=cast(Any, model_info),
        message_list=[],
    )
    client = FilteredClient()
    orchestrator = object.__new__(LLMOrchestrator)
    orchestrator.request_type = "maisaka.replyer"

    with pytest.raises(ModelAttemptFailed) as exc_info:
        await orchestrator._attempt_request_on_model(
            cast(Any, provider),
            cast(Any, client),
            request,
        )

    assert client.calls == 1
    assert isinstance(exc_info.value.original_exception, ContentFilterException)


@pytest.mark.asyncio
async def test_orchestrator_falls_back_to_next_model_after_content_filter() -> None:
    class FilteredClient:
        def __init__(self) -> None:
            self.calls = 0

        async def get_response(self, request: ResponseRequest) -> APIResponse:
            del request
            self.calls += 1
            raise ContentFilterException(message="响应被上游内容审核拦截")

    class HealthyClient:
        def __init__(self) -> None:
            self.calls = 0

        async def get_response(self, request: ResponseRequest) -> APIResponse:
            del request
            self.calls += 1
            return APIResponse(content="正常回复")

    provider = SimpleNamespace(max_retry=3, retry_interval=0)
    filtered_model = SimpleNamespace(name="freedsv4f")
    healthy_model = SimpleNamespace(name="gemini-sp-2")
    filtered_client = FilteredClient()
    healthy_client = HealthyClient()
    candidates = {
        "freedsv4f": (filtered_model, provider, filtered_client),
        "gemini-sp-2": (healthy_model, provider, healthy_client),
    }

    orchestrator = object.__new__(LLMOrchestrator)
    orchestrator.task_name = "replyer"
    orchestrator.request_type = "maisaka.replyer"
    orchestrator.model_for_task = SimpleNamespace(
        model_list=["freedsv4f", "gemini-sp-2"],
        selection_strategy="sequential",
        hard_timeout=5,
    )
    orchestrator.model_usage = {
        "freedsv4f": (0, 0, 0),
        "gemini-sp-2": (0, 0, 0),
    }

    def select_model(exclude_models: set[str], model_name: str | None = None) -> Any:
        del model_name
        for candidate_name in orchestrator.model_for_task.model_list:
            if candidate_name not in exclude_models:
                return candidates[candidate_name]
        raise RuntimeError("没有可用候选模型")

    def build_client_request(**kwargs: Any) -> ResponseRequest:
        return ResponseRequest(
            model_info=kwargs["model_info"],
            message_list=kwargs["message_list"],
        )

    orchestrator._select_model = cast(Any, select_model)
    orchestrator._build_client_request = cast(Any, build_client_request)

    result = await orchestrator._execute_request(
        RequestType.RESPONSE,
        message_factory=lambda _client: [],
    )

    assert result.api_response.content == "正常回复"
    assert result.model_info.name == "gemini-sp-2"
    assert filtered_client.calls == 1
    assert healthy_client.calls == 1
