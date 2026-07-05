#!/usr/bin/env python3
"""快速测试配置是否能正确加载。"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))


def test_config_loading():
    """测试配置加载。"""
    print("=" * 60)
    print("测试配置加载")
    print("=" * 60)

    try:
        from src.config.config import config_manager

        print("[OK] 配置管理器导入成功")

        # 获取配置
        global_config = config_manager.get_global_config()
        print("[OK] global_config 加载成功")

        # 检查 features 配置
        if hasattr(global_config, "features"):
            print("[OK] features 配置存在")
            features = global_config.features

            if hasattr(features, "seiyuu_recognition"):
                print("[OK] seiyuu_recognition 配置存在")
                seiyuu_config = features.seiyuu_recognition

                print(f"  - enabled: {seiyuu_config.enabled}")
                print(f"  - api_endpoint: {seiyuu_config.api_endpoint}")
                print(f"  - timeout: {seiyuu_config.timeout}")
                print(f"  - selected_groups: {seiyuu_config.selected_groups}")
            else:
                print("[FAIL] seiyuu_recognition 配置不存在")
                return False
        else:
            print("[FAIL] features 配置不存在")
            return False

        print("\n" + "=" * 60)
        print("配置加载测试通过！")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\n[FAIL] 配置加载失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_config_loading()
    sys.exit(0 if success else 1)
