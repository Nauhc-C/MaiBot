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
        self._selected_groups = "bangdream:mygo,bangdream:avemujica,bangdream:roselia"
        self._enable_fallback = True  # 是否启用回退机制
        self._fallback_threshold = 60  # 回退阈值（置信度低于此值时触发）

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

                    # 读取回退配置
                    if hasattr(seiyuu_config, "enable_fallback"):
                        self._enable_fallback = seiyuu_config.enable_fallback
                    if hasattr(seiyuu_config, "fallback_threshold"):
                        self._fallback_threshold = seiyuu_config.fallback_threshold
        except Exception as exc:
            logger.debug(f"读取 SeiyuuMatch 配置失败，将使用默认配置: {exc}")

        if self._enabled:
            fallback_status = "启用" if self._enable_fallback else "禁用"
            logger.info(
                f"SeiyuuMatch 识别已启用，API: {self._api_endpoint}, "
                f"groups: {self._selected_groups}, 回退机制: {fallback_status}"
            )
        else:
            logger.debug("SeiyuuMatch 识别未启用")

    async def recognize(self, image_bytes: bytes) -> Optional[dict]:
        """识别图片中的声优角色，带三级回退机制。

        Args:
            image_bytes: 图片二进制数据

        Returns:
            识别结果字典，包含 faces、details 和 fallback_level 字段；
            如果未启用、识别失败或无人脸，返回 None
        """
        if not self._enabled:
            return None

        # 定义三级回退范围
        fallback_levels = self._get_fallback_levels()

        # 逐级尝试识别
        for level, groups in enumerate(fallback_levels, 1):
            result = await self._recognize_with_groups(image_bytes, groups)

            if result is None:
                # API 错误，直接返回
                return None

            # 检查识别结果
            details = result.get("details", [])
            if not details:
                # 无人脸，直接返回
                logger.info("SeiyuuMatch 未识别到人脸")
                return None

            # 计算平均置信度
            avg_score = sum(d.get("display_score", 0) for d in details) / len(details)

            # 记录当前级别
            result["fallback_level"] = level
            result["fallback_groups"] = groups

            # 判断是否需要回退
            if avg_score >= self._fallback_threshold:
                # 置信度足够，返回结果
                names = result.get("faces", [])
                logger.info(
                    f"SeiyuuMatch 识别成功 (级别 {level}): {len(details)} 个人脸 - {', '.join(names)} "
                    f"(平均置信度 {int(avg_score)}%)"
                )
                return result

            # 置信度不足，判断是否继续回退
            if self._enable_fallback and level < len(fallback_levels):
                logger.info(
                    f"SeiyuuMatch 识别置信度不足 (级别 {level}: {int(avg_score)}% < {self._fallback_threshold}%)，"
                    f"尝试扩大识别范围到级别 {level + 1}"
                )
                continue
            else:
                # 已达到最后一级或未启用回退，返回当前结果
                names = result.get("faces", [])
                if self._enable_fallback:
                    logger.info(
                        f"SeiyuuMatch 识别完成 (级别 {level}，最终): {len(details)} 个人脸 - {', '.join(names)} "
                        f"(平均置信度 {int(avg_score)}%)"
                    )
                else:
                    logger.info(
                        f"SeiyuuMatch 识别完成: {len(details)} 个人脸 - {', '.join(names)} "
                        f"(置信度 {int(avg_score)}%，未启用回退)"
                    )
                return result

        # 不应该到达这里
        return None

    def _get_fallback_levels(self) -> list[str]:
        """获取三级回退的识别范围。

        Returns:
            三个级别的 groups 配置列表
        """
        # 级别 1: 用户配置的初始范围（通常是 3 个团）
        level1 = self._selected_groups

        # 级别 2: 中等范围（5-7 个团）
        # 在初始范围基础上增加 Roselia, RAS, Morfonica
        base_groups = set(level1.split(","))
        additional_groups = {
            "bangdream:roselia",
            "bangdream:ras",
            "bangdream:morfonica",
        }
        level2_groups = base_groups | additional_groups
        level2 = ",".join(sorted(level2_groups))

        # 级别 3: 全 BanG Dream 范围（13 个团）
        all_bangdream_groups = [
            "bangdream:mygo",
            "bangdream:avemujica",
            "bangdream:sumimi",
            "bangdream:roselia",
            "bangdream:afterglow",
            "bangdream:pastel",
            "bangdream:hhw",
            "bangdream:ras",
            "bangdream:morfonica",
            "bangdream:ppp",
            "bangdream:dumbrock",
            "bangdream:mewtype",
            "bangdream:millsage",
        ]
        level3 = ",".join(all_bangdream_groups)

        return [level1, level2, level3]

    async def _recognize_with_groups(self, image_bytes: bytes, groups: str) -> Optional[dict]:
        """使用指定的 groups 进行识别。

        Args:
            image_bytes: 图片字节数据
            groups: 识别范围，例如 "bangdream:mygo,bangdream:avemujica"

        Returns:
            识别结果字典，如果 API 错误则返回 None
        """
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    self._api_endpoint,
                    params={"groups": groups},
                    content=image_bytes,
                    headers={"Content-Type": "image/jpeg"},
                )
                response.raise_for_status()
                result = response.json()
                return result

        except httpx.TimeoutException:
            logger.warning(f"SeiyuuMatch API 请求超时 (timeout={self._timeout}s)")
            return None
        except httpx.HTTPStatusError as exc:
            logger.warning(f"SeiyuuMatch API 返回错误: {exc.response.status_code}")
            return None
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
            bbox = detail.get("bbox", [])

            # 计算位置信息
            position = self._get_face_position(bbox, len(details), idx)

            # 构建角色信息
            info_parts = [name]
            if project and group:
                info_parts.append(f"来自 {project}/{group}")
            elif project:
                info_parts.append(f"来自 {project}")

            # 构建单个人脸描述
            if len(details) > 1:
                # 多人脸场景：标注位置
                parts.append(
                    f"{position}的人物: {', '.join(info_parts)}（识别置信度 {score}%）"
                )
            else:
                # 单人脸场景
                parts.append(f"人物: {', '.join(info_parts)}（识别置信度 {score}%）")

        result = "【人脸识别结果】" + "；".join(parts) + "。"

        # 添加置信度提示
        avg_score = sum(d.get("display_score", 0) for d in details) / len(details)
        if avg_score < 70:
            result += "\n注意：识别置信度较低，请结合图片内容综合判断。"

        return result

    def _get_face_position(self, bbox: list, total_faces: int, face_index: int) -> str:
        """根据 bbox 计算人脸在图片中的位置。

        Args:
            bbox: [x1, y1, x2, y2] 归一化坐标 (0-1)
            total_faces: 总人脸数
            face_index: 当前人脸索引（从 1 开始）

        Returns:
            位置描述，如 "图左侧"、"图中央"、"图右侧"
        """
        if not bbox or len(bbox) < 4:
            return "图中"

        if total_faces == 1:
            return "图中"

        # 计算人脸中心点的 x 坐标
        center_x = (bbox[0] + bbox[2]) / 2

        # 根据 x 坐标判断位置
        if center_x < 0.33:
            return "图左侧"
        elif center_x > 0.67:
            return "图右侧"
        else:
            return "图中央"


seiyuu_recognizer = SeiyuuRecognizer()
