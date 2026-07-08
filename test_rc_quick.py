"""快速测试 right.codes API"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.maisaka.builtin_tool.generate_image import ImageGenerator

async def test():
    print("测试 right.codes gpt-image-2 API")
    print("=" * 60)

    generator = ImageGenerator()
    print(f"API: {generator.base_url}")
    print(f"模型: {generator.model}")

    prompt = "一只可爱的小猫在阳光下"
    print(f"\n提示词: {prompt}")
    print("开始生成...")

    result = await generator.generate(prompt)

    if result:
        print(f"\n成功! 图像大小: {len(result)} 字节")

        output = Path("output/test_rc_final.png")
        output.parent.mkdir(exist_ok=True)
        output.write_bytes(result)
        print(f"已保存到: {output}")
    else:
        print("\n失败!")

if __name__ == "__main__":
    asyncio.run(test())
