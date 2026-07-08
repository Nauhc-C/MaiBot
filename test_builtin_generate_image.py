"""测试图像生成内置工具。"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.maisaka.builtin_tool.generate_image import get_tool_spec, ImageGenerator


async def test_tool_spec():
    """测试工具规范"""
    print("=" * 60)
    print("测试 1: 工具规范")
    print("=" * 60)

    spec = get_tool_spec()
    print(f"工具名称: {spec.name}")
    print(f"工具描述: {spec.description}")
    print(f"提供商: {spec.provider_name}")
    print(f"参数: {list(spec.parameters_schema['properties'].keys())}")
    print(f"必需参数: {spec.parameters_schema.get('required', [])}")
    print("[OK] 工具规范正常\n")


async def test_image_generator():
    """测试图像生成器"""
    print("=" * 60)
    print("测试 2: 图像生成器")
    print("=" * 60)

    generator = ImageGenerator()
    print(f"API URL: {generator.base_url}")
    print(f"模型: {generator.model}")
    print(f"超时: {generator.timeout}s")

    # 测试生成
    prompt = "一只可爱的小猫，卡通风格"
    print(f"\n开始生成图像...")
    print(f"提示词: {prompt}")

    result = await generator.generate(prompt)

    if result:
        print(f"[OK] 生成成功")
        print(f"图像大小: {len(result)} 字节 ({len(result) // 1024} KB)")

        # 保存测试图像
        output_path = Path("output/test_builtin_tool.png")
        output_path.parent.mkdir(exist_ok=True)
        output_path.write_bytes(result)
        print(f"已保存到: {output_path}")
    else:
        print("[FAIL] 生成失败")


async def test_import():
    """测试导入"""
    print("=" * 60)
    print("测试 3: 模块导入")
    print("=" * 60)

    try:
        from src.maisaka.builtin_tool import get_all_builtin_tool_specs

        specs = get_all_builtin_tool_specs()
        tool_names = [spec.name for spec in specs]

        print(f"共加载 {len(specs)} 个内置工具:")
        for name in tool_names:
            print(f"  - {name}")

        if "generate_image" in tool_names:
            print("\n[OK] generate_image 已成功注册")
        else:
            print("\n[FAIL] generate_image 未找到")

    except Exception as e:
        print(f"[FAIL] 导入失败: {e}")
        import traceback

        traceback.print_exc()


async def main():
    """主函数"""
    print("图像生成内置工具测试\n")

    try:
        # 测试 1: 工具规范
        await test_tool_spec()

        # 测试 2: 图像生成（可选，需要网络）
        print("是否测试实际生成？(y/N): ", end="")
        choice = input().strip().lower()
        if choice == "y":
            await test_image_generator()
        else:
            print("跳过实际生成测试\n")

        # 测试 3: 导入
        await test_import()

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)

    except KeyboardInterrupt:
        print("\n测试被中断")
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
