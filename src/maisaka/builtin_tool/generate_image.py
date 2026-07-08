"""图片生成内置工具。"""

import asyncio
import base64
import json
import urllib.request
from typing import Any, Optional

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
    """图像生成器，使用 right.codes gpt-image-2 API（异步模式）"""

    def __init__(self):
        # 使用 right.codes API
        self.base_url = "https://www.right.codes/draw"
        self.api_key = "REDACTED_USE_ENV"
        self.model = "gpt-image-2"
        self.timeout = 120  # 任务查询超时
        self.poll_interval = 2  # 轮询间隔（秒）

    async def generate(self, prompt: str) -> bytes | None:
        """生成图像

        Args:
            prompt: 图像描述提示词

        Returns:
            图像二进制数据，失败返回 None
        """
        try:
            # 步骤1: 提交生图任务
            task_id = await asyncio.to_thread(self._submit_task, prompt)
            if not task_id:
                logger.error("提交生图任务失败")
                return None

            logger.info(f"生图任务已提交，task_id: {task_id}")

            # 步骤2: 轮询任务状态
            image_url = await self._poll_task_result(task_id)
            if not image_url:
                logger.error("获取生图结果失败")
                return None

            logger.info(f"生图完成，图片 URL: {image_url}")

            # 步骤3: 下载图片
            image_data = await asyncio.to_thread(self._download_image, image_url)
            return image_data

        except Exception as e:
            logger.error(f"图像生成失败: {e}", exc_info=True)
            return None

    def _submit_task(self, prompt: str) -> str | None:
        """提交生图任务

        Returns:
            task_id 或 None
        """
        url = f"{self.base_url}/v1/images/generations"
        body = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": "1:1",
            "async": True,  # 异步模式
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

        request = urllib.request.Request(
            url=url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            logger.error(f"提交任务失败 HTTP {exc.code}: {detail}")
            return None

        data = json.loads(response_body.decode("utf-8"))
        return data.get("task_id")

    async def _poll_task_result(self, task_id: str) -> str | None:
        """轮询任务结果

        Returns:
            图片 URL 或 None
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            # 检查超时
            if asyncio.get_event_loop().time() - start_time > self.timeout:
                logger.error(f"任务 {task_id} 查询超时")
                return None

            # 查询任务状态
            result = await asyncio.to_thread(self._query_task, task_id)

            if result is None:
                # 查询失败
                return None

            status = result.get("status", "")

            if status == "failed":
                error_msg = result.get("error", {}).get("message", "未知错误")
                logger.error(f"任务 {task_id} 失败: {error_msg}")
                return None

            if status in ["queued", "in_progress"]:
                # 任务进行中，继续轮询
                progress = result.get("progress", 0)
                logger.debug(f"任务 {task_id} 进度: {progress}%")
                await asyncio.sleep(self.poll_interval)
                continue

            # 任务完成，提取图片 URL
            if "data" in result:
                # Images 格式
                data_list = result.get("data", [])
                if data_list and len(data_list) > 0:
                    return data_list[0].get("url")
            elif "candidates" in result:
                # Gemini 格式
                candidates = result.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")
                        if text.startswith("http"):
                            return text

            logger.error(f"任务 {task_id} 响应格式异常: {result}")
            return None

    def _query_task(self, task_id: str) -> dict[str, Any] | None:
        """查询任务状态

        Returns:
            任务状态字典或 None
        """
        url = f"https://www.right.codes/v1/tasks/{task_id}"

        request = urllib.request.Request(
            url=url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            logger.error(f"查询任务失败 HTTP {exc.code}: {detail}")
            return None

        return json.loads(response_body.decode("utf-8"))

    def _download_image(self, image_url: str) -> bytes:
        """下载图片

        Returns:
            图片二进制数据
        """
        request = urllib.request.Request(
            url=image_url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
        )

        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()


# 全局生成器实例（复用连接）
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

    # 构建完整提示词
    full_prompt = prompt
    if style_hint:
        full_prompt = f"{prompt}，{style_hint}"

    logger.info(f"{tool_ctx.runtime.log_prefix} 开始生成图像，提示词: {full_prompt}")

    # 生成图像
    generator = _get_generator()
    try:
        image_data = await generator.generate(full_prompt)
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
