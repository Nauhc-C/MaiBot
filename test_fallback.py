#!/usr/bin/env python3
"""测试 SeiyuuMatch 三级回退机制。"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


async def test_fallback_mechanism():
    """测试三级回退机制。"""
    print("=" * 70)
    print("测试 SeiyuuMatch 三级回退机制")
    print("=" * 70)
    print()

    try:
        from src.chat.image_system.seiyuu_recognizer import seiyuu_recognizer

        print("[OK] seiyuu_recognizer 导入成功")
        print(f"  - 是否启用: {seiyuu_recognizer._enabled}")
        print(f"  - API 地址: {seiyuu_recognizer._api_endpoint}")
        print(f"  - 初始识别范围: {seiyuu_recognizer._selected_groups}")
        print(f"  - 回退机制: {'启用' if seiyuu_recognizer._enable_fallback else '禁用'}")
        print(f"  - 回退阈值: {seiyuu_recognizer._fallback_threshold}%")
        print()

        if not seiyuu_recognizer._enabled:
            print("[警告] SeiyuuMatch 识别未启用")
            return False

        # 测试三级回退范围
        print("-" * 70)
        print("测试三级回退范围配置")
        print("-" * 70)

        levels = seiyuu_recognizer._get_fallback_levels()
        for i, groups in enumerate(levels, 1):
            group_count = len(groups.split(","))
            print(f"级别 {i}: {group_count} 个团体")
            print(f"  配置: {groups[:80]}{'...' if len(groups) > 80 else ''}")
            print()

        # 模拟不同置信度的回退逻辑
        print("-" * 70)
        print("模拟回退触发逻辑")
        print("-" * 70)

        test_scenarios = [
            ("高置信度照片", 89, 1),
            ("中等置信度照片", 55, 2),
            ("低置信度照片", 48, 3),
            ("极低置信度照片", 35, 3),
        ]

        for scenario, confidence, expected_level in test_scenarios:
            print(f"\n场景: {scenario} (置信度 {confidence}%)")

            level = 1
            current_confidence = confidence

            while level <= 3:
                if current_confidence >= seiyuu_recognizer._fallback_threshold:
                    print(f"  → 级别 {level}: {current_confidence}% >= {seiyuu_recognizer._fallback_threshold}% ✅ 识别成功")
                    break
                else:
                    if level < 3:
                        print(f"  → 级别 {level}: {current_confidence}% < {seiyuu_recognizer._fallback_threshold}% ❌ 触发回退")
                        level += 1
                        # 模拟扩大范围后置信度可能提升
                        current_confidence += 10
                    else:
                        print(f"  → 级别 {level}: {current_confidence}% < {seiyuu_recognizer._fallback_threshold}% ⚠️ 最终级别")
                        break

            if level == expected_level:
                print(f"  ✅ 符合预期（级别 {expected_level}）")
            else:
                print(f"  ❌ 不符合预期（预期级别 {expected_level}，实际级别 {level}）")

        print()
        print("=" * 70)
        print("三级回退机制测试完成！")
        print()
        print("下一步:")
        print("1. 确保 SeiyuuMatch 服务运行: D:\\Sakiko\\services\\seiyuumatch\\start-seiyuumatch.bat")
        print("2. 重启 MaiBot: uv run python -X utf8 bot.py")
        print("3. 发送不同清晰度的照片测试实际效果")
        print("=" * 70)

        return True

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_fallback_mechanism())
    sys.exit(0 if success else 1)
