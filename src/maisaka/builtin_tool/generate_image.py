"""图片生成内置工具。"""

from os import getenv
from typing import Any, Optional
import base64

import httpx

from src.common.logger import get_logger
from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.services import send_service

from .context import BuiltinToolRuntimeContext

logger = get_logger("maisaka_builtin_generate_image")


def get_tool_spec() -> ToolSpec:
    """获取图片生成工具声明。"""

    return ToolSpec(
        name="generate_image",
        description=(
            "根据文字描述生成图像。当你需要创作、绘制、画图时使用。"
            "可以生成风景、人物、场景等各种类型的图片。"
            "生成的图片会自动发送给用户。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "图像描述提示词，描述你想要生成的图像内容、风格、氛围等。",
                },
                "style_hint": {
                    "type": "string",
                    "description": "可选的风格提示，例如：动漫风格、写实风格、水彩画风格等。",
                    "default": "",
                },
            },
            "required": ["prompt"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


class ImageGenerator:
    """独立生图服务客户端。"""

    def __init__(
        self,
        base_url: str | None = None,
        service_token: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.base_url = (
            base_url or getenv("IMAGE_GENERATION_SERVICE_URL", "http://127.0.0.1:8091")
        ).rstrip("/")
        self.service_token = (
            service_token if service_token is not None else getenv("IMAGE_GENERATION_SERVICE_TOKEN", "").strip()
        )
        self.timeout = (
            timeout
            if timeout is not None
            else float(getenv("IMAGE_GENERATION_SERVICE_TIMEOUT_SECONDS", "150"))
        )
        self._client = client

    async def generate(self, prompt: str, style_hint: str = "") -> bytes:
        """调用独立服务生成图片并返回二进制数据。"""

        headers: dict[str, str] = {}
        if self.service_token:
            headers["Authorization"] = f"Bearer {self.service_token}"
        request_body = {
            "prompt": prompt,
            "style_hint": style_hint,
            "size": "1:1",
        }

        if self._client is not None:
            response = await self._client.post(
                f"{self.base_url}/v1/images/generations",
                headers=headers,
                json=request_body,
                timeout=self.timeout,
            )
        else:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/images/generations",
                    headers=headers,
                    json=request_body,
                )

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            try:
                error_payload = response.json()
            except ValueError:
                detail = response.text
            else:
                detail = (
                    str(error_payload.get("detail") or response.text)
                    if isinstance(error_payload, dict)
                    else response.text
                )
            raise RuntimeError(f"生图服务返回 HTTP {response.status_code}: {detail[:500]}") from exc

        if not response.content:
            raise RuntimeError("生图服务返回了空图片")
        content_type = response.headers.get("content-type", "").lower()
        if not content_type.startswith("image/"):
            raise RuntimeError(f"生图服务返回了非图片内容: {content_type or 'unknown'}")
        return response.content


# 全局客户端实例（复用服务配置）
_generator: ImageGenerator | None = None


def _get_generator() -> ImageGenerator:
    """获取全局生成器实例"""
    global _generator
    if _generator is None:
        _generator = ImageGenerator()
    return _generator


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行图片生成内置动作。"""

    del context
    arguments = dict(invocation.arguments or {})
    prompt = str(arguments.get("prompt", "")).strip()
    style_hint = str(arguments.get("style_hint", "")).strip()

    structured_content: dict[str, Any] = {
        "success": False,
        "stream_id": tool_ctx.runtime.session_id,
        "prompt": prompt,
    }

    # 验证参数
    if not prompt:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "生成图像需要提供描述提示词",
            structured_content=structured_content,
        )

    # 构建日志中展示的完整提示词，实际组合由独立服务完成
    full_prompt = prompt
    if style_hint:
        full_prompt = f"{prompt}，{style_hint}"

    logger.info(f"{tool_ctx.runtime.log_prefix} 开始生成图像，提示词: {full_prompt}")

    # 生成图像
    generator = _get_generator()
    try:
        image_data = await generator.generate(prompt, style_hint=style_hint)
    except Exception as e:
        logger.error(f"{tool_ctx.runtime.log_prefix} 图像生成异常: {e}", exc_info=True)
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            f"图像生成失败: {str(e)}",
            structured_content=structured_content,
        )

    if not image_data:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "图像生成失败：API 返回空数据",
            structured_content=structured_content,
        )

    logger.info(f"{tool_ctx.runtime.log_prefix} 图像生成成功，大小: {len(image_data)} 字节")

    # 发送图像到聊天流
    image_base64 = base64.b64encode(image_data).decode("utf-8")
    success = await send_service.image_to_stream(
        image_base64=image_base64,
        stream_id=tool_ctx.runtime.session_id,
        sync_to_maisaka_history=True,
        maisaka_source_kind="generate_image",
    )

    if not success:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "图像生成成功但发送失败",
            structured_content=structured_content,
        )

    structured_content["success"] = True
    structured_content["image_size"] = len(image_data)

    return tool_ctx.build_success_result(
        invocation.tool_name,
        f"已生成并发送图像（{len(image_data) // 1024} KB）",
        structured_content=structured_content,
    )
