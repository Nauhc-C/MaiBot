#!/usr/bin/env python3
"""测试 SeiyuuMatch 识别集成。

使用方法:
    python test_seiyuu_recognition.py <图片路径>

示例:
    python test_seiyuu_recognition.py test_images/ritsu.jpg
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


async def test_recognition(image_path: str):
    """测试 SeiyuuMatch 识别功能。"""
    from src.chat.image_system.seiyuu_recognizer import seiyuu_recognizer
    from src.common.logger import get_logger

    logger = get_logger("test")

    # 读取图片
    image_file = Path(image_path)
    if not image_file.exists():
        logger.error(f"图片文件不存在: {image_path}")
        return

    with open(image_file, "rb") as f:
        image_bytes = f.read()

    logger.info(f"正在识别图片: {image_path} ({len(image_bytes)} bytes)")

    # 调用识别
    result = await seiyuu_recognizer.recognize(image_bytes)

    if result:
        logger.info("=" * 60)
        logger.info("识别成功！")
        logger.info(f"识别到 {len(result['faces'])} 个人脸")
        logger.info("-" * 60)

        for idx, detail in enumerate(result.get("details", []), 1):
            name = detail.get("name", "未知")
            project = detail.get("project", "")
            group = detail.get("group", "")
            score = detail.get("display_score", 0)

            logger.info(f"人物 {idx}: {name}")
            logger.info(f"  项目: {project}")
            logger.info(f"  团体: {group}")
            logger.info(f"  相似度: {score}%")

            if "top5" in detail:
                logger.info("  Top 5 候选:")
                for rank, candidate in enumerate(detail["top5"][:5], 1):
                    logger.info(
                        f"    {rank}. {candidate['name']} "
                        f"({candidate.get('display_score', 0)}%)"
                    )
            logger.info("-" * 60)

        # 测试 prompt 格式化
        formatted = seiyuu_recognizer.format_recognition_for_prompt(result)
        logger.info("格式化后的 Prompt 注入文本:")
        logger.info(formatted)
        logger.info("=" * 60)
    else:
        logger.warning("未识别到人脸或识别失败")


async def test_image_description(image_path: str):
    """测试完整的图片描述生成流程（包含 SeiyuuMatch 识别）。"""
    from src.chat.image_system.image_manager import image_manager
    from src.common.logger import get_logger

    logger = get_logger("test")

    # 读取图片
    image_file = Path(image_path)
    if not image_file.exists():
        logger.error(f"图片文件不存在: {image_path}")
        return

    with open(image_file, "rb") as f:
        image_bytes = f.read()

    logger.info(f"\n{'=' * 60}")
    logger.info("测试完整图片描述生成流程")
    logger.info(f"图片: {image_path}")
    logger.info(f"{'=' * 60}\n")

    # 生成描述（会自动调用 SeiyuuMatch 识别）
    description = await image_manager.get_image_description(
        image_bytes=image_bytes,
        wait_for_build=True,
    )

    logger.info(f"\n{'=' * 60}")
    logger.info("生成的图片描述:")
    logger.info(description)
    logger.info(f"{'=' * 60}\n")


def main():
    """主函数。"""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    image_path = sys.argv[1]

    print("\n" + "=" * 60)
    print("SeiyuuMatch 识别测试")
    print("=" * 60 + "\n")

    # 测试识别
    asyncio.run(test_recognition(image_path))

    # 测试完整流程
    print("\n按 Enter 继续测试完整图片描述生成流程（需要配置 VLM）...")
    input()
    asyncio.run(test_image_description(image_path))


if __name__ == "__main__":
    main()
