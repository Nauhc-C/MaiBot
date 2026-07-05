"""SeiyuuMatch 人脸识别集成模块。

在图片描述生成前识别照片中的声优角色，提供准确的角色信息给 VLM。
"""

import asyncio
from typing import Optional

import httpx

from src.common.logger import get_logger
from src.config.config import config_manager

logger = get_logger("seiyuu_recognizer")


class SeiyuuRecognizer:
    """SeiyuuMatch API 客户端。"""

    def __init__(self) -> None:
        """初始化识别器。"""
        self._enabled = False
        self._api_endpoint = ""
        self._timeout = 10.0
        self._selected_groups = "bangdream:mygo,bangdream:avemujica,bangdream:sumimi"

        try:
            global_config = config_manager.get_global_config()
            if hasattr(global_config, "features"):
                features_config = global_config.features
                if hasattr(features_config, "seiyuu_recognition"):
                    seiyuu_config = features_config.seiyuu_recognition
                    self._enabled = seiyuu_config.enabled
                    self._api_endpoint = seiyuu_config.api_endpoint
                    self._timeout = seiyuu_config.timeout
                    self._selected_groups = seiyuu_config.selected_groups
        except Exception as exc:
            logger.debug(f"读取 SeiyuuMatch 配置失败，将使用默认配置: {exc}")

        if self._enabled:
            logger.info(
                f"SeiyuuMatch 识别已启用，API: {self._api_endpoint}, "
                f"groups: {self._selected_groups}"
            )
        else:
            logger.debug("SeiyuuMatch 识别未启用")

    async def recognize(self, image_bytes: bytes) -> Optional[dict]:
        """识别图片中的声优角色。

        Args:
            image_bytes: 图片二进制数据

        Returns:
            识别结果字典，包含 faces 和 details 字段；
            如果未启用、识别失败或无人脸，返回 None
        """
        if not self._enabled:
            return None

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._api_endpoint,
                    params={"groups": self._selected_groups},
                    content=image_bytes,
                    headers={"Content-Type": "image/jpeg"},
                )
                response.raise_for_status()
                result = response.json()

                # 检查是否有识别结果
                if not result.get("faces") or not result.get("details"):
                    logger.debug("SeiyuuMatch 未识别到人脸")
                    return None

                logger.info(
                    f"SeiyuuMatch 识别成功: {len(result['faces'])} 个人脸 - "
                    f"{', '.join(result['faces'])}"
                )
                return result

        except httpx.TimeoutException:
            logger.warning(f"SeiyuuMatch API 请求超时 (timeout={self._timeout}s)")
        except httpx.HTTPStatusError as exc:
            logger.warning(f"SeiyuuMatch API 返回错误: {exc.response.status_code}")
        except Exception as exc:
            logger.warning(f"SeiyuuMatch 识别失败: {exc}")

        return None

    def format_recognition_for_prompt(self, recognition_result: dict) -> str:
        """将识别结果格式化为 prompt 注入文本。

        Args:
            recognition_result: SeiyuuMatch API 返回的识别结果

        Returns:
            格式化的文本，用于注入到图片描述 prompt 中
        """
        details = recognition_result.get("details", [])
        if not details:
            return ""

        parts = []
        for idx, detail in enumerate(details, 1):
            name = detail.get("name", "未知")
            project = detail.get("project", "")
            group = detail.get("group", "")
            score = detail.get("display_score", 0)

            # 构建角色信息
            info_parts = [name]
            if project and group:
                info_parts.append(f"来自 {project}/{group}")
            elif project:
                info_parts.append(f"来自 {project}")

            if len(details) > 1:
                parts.append(f"人物{idx}: {', '.join(info_parts)}（相似度 {score}%）")
            else:
                parts.append(f"人物: {', '.join(info_parts)}（相似度 {score}%）")

        return "【人脸识别结果】" + "；".join(parts) + "。"


seiyuu_recognizer = SeiyuuRecognizer()
