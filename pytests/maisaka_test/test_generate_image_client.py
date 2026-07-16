"""独立生图服务客户端测试。"""

import json

import httpx
import pytest

from src.maisaka.builtin_tool.generate_image import ImageGenerator


@pytest.mark.asyncio
async def test_generate_image_client_forwards_prompt_style_and_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("http://image-service:8091/v1/images/generations")
        assert request.headers["Authorization"] == "Bearer service-token"
        assert json.loads(request.content) == {
            "prompt": "雨夜街道",
            "style_hint": "动画电影风格",
            "size": "1:1",
        }
        return httpx.Response(200, content=b"generated-image", headers={"Content-Type": "image/png"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        generator = ImageGenerator(
            base_url="http://image-service:8091/",
            service_token="service-token",
            timeout=10,
            client=client,
        )
        image_data = await generator.generate("雨夜街道", style_hint="动画电影风格")

    assert image_data == b"generated-image"


@pytest.mark.asyncio
async def test_generate_image_client_reports_service_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "upstream failed"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        generator = ImageGenerator(base_url="http://image-service:8091", client=client)
        with pytest.raises(RuntimeError, match="upstream failed"):
            await generator.generate("prompt")


@pytest.mark.asyncio
async def test_generate_image_client_rejects_non_image_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "payload"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        generator = ImageGenerator(base_url="http://image-service:8091", client=client)
        with pytest.raises(RuntimeError, match="非图片内容"):
            await generator.generate("prompt")
