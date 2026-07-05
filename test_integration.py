#!/usr/bin/env python3
"""端到端测试：验证 SeiyuuMatch 集成是否正常工作。"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


async def test_seiyuu_recognizer():
    """测试 SeiyuuMatch 识别器初始化。"""
    print("=" * 60)
    print("测试 SeiyuuMatch 识别器")
    print("=" * 60)

    try:
        from src.chat.image_system.seiyuu_recognizer import seiyuu_recognizer

        print("[OK] seiyuu_recognizer 导入成功")
        print(f"  - 是否启用: {seiyuu_recognizer._enabled}")
        print(f"  - API 地址: {seiyuu_recognizer._api_endpoint}")
        print(f"  - 超时时间: {seiyuu_recognizer._timeout}s")
        print(f"  - 识别范围: {seiyuu_recognizer._selected_groups}")

        if not seiyuu_recognizer._enabled:
            print("\n[警告] SeiyuuMatch 识别未启用")
            print("请在 config/bot_config.toml 中设置:")
            print("  [features.seiyuu_recognition]")
            print("  enabled = true")
            return False

        print("\n" + "=" * 60)
        print("SeiyuuMatch 识别器测试通过！")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[FAIL] 识别器初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_image_manager_integration():
    """测试 image_manager 集成。"""
    print("\n" + "=" * 60)
    print("测试 image_manager 集成")
    print("=" * 60)

    try:
        from src.chat.image_system.image_manager import image_manager

        print("[OK] image_manager 导入成功")

        # 检查 _generate_image_description 方法是否包含 seiyuu_recognizer
        import inspect
        source = inspect.getsource(image_manager._generate_image_description)

        if "seiyuu_recognizer" in source:
            print("[OK] _generate_image_description 已集成 seiyuu_recognizer")
        else:
            print("[FAIL] _generate_image_description 未集成 seiyuu_recognizer")
            return False

        print("\n" + "=" * 60)
        print("image_manager 集成测试通过！")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[FAIL] image_manager 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数。"""
    print("\n" + "=" * 70)
    print("SeiyuuMatch 集成端到端测试")
    print("=" * 70 + "\n")

    # 测试识别器
    recognizer_ok = await test_seiyuu_recognizer()

    # 测试 image_manager 集成
    integration_ok = await test_image_manager_integration()

    # 总结
    print("\n" + "=" * 70)
    if recognizer_ok and integration_ok:
        print("✓ 所有测试通过！SeiyuuMatch 集成已就绪。")
        print("\n下一步:")
        print("1. 重启 MaiBot: uv run python -X utf8 bot.py")
        print("2. 发送包含声优照片的消息进行实际测试")
    else:
        print("✗ 部分测试失败，请检查上述错误信息")
    print("=" * 70 + "\n")

    return recognizer_ok and integration_ok


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
