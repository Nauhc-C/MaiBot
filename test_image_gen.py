"""独立的图像生成测试脚本

使用 gpt-image-2 API 进行图像生成测试。
测试完成后再接入 MaiBot。
"""

import asyncio
import base64
import json
import logging
import sys
import urllib.request
from pathlib import Path
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('image_gen_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class SimpleImageGenerator:
    """简化版图像生成器，仅使用 gpt-image-2"""

    def __init__(self, base_url: str, api_key: str, timeout: int = 60):
        """初始化生成器

        Args:
            base_url: API 基础 URL
            api_key: API 密钥
            timeout: 请求超时秒数
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

    async def generate_image(
        self,
        prompt: str,
        reference_images: list[Path] | None = None,
        output_path: Path | None = None,
    ) -> bytes | None:
        """生成图像

        Args:
            prompt: 提示词
            reference_images: 参考图像文件路径列表（可选）
            output_path: 输出文件路径（可选，不指定则只返回二进制数据）

        Returns:
            生成的图像二进制数据，失败返回 None
        """
        logger.info(f"开始生成图像，提示词: {prompt}")

        # 构建请求体
        body: dict[str, Any] = {
            "model": "gpt-image-2",
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        }

        # 添加参考图（如果提供）
        if reference_images:
            references = []
            for idx, img_path in enumerate(reference_images, 1):
                if not img_path.exists():
                    logger.warning(f"参考图 #{idx} 不存在: {img_path}")
                    continue

                data_url = self._image_to_data_url(img_path)
                if data_url:
                    references.append(data_url)
                    logger.info(f"添加参考图 #{idx}: {img_path.name}")

            if references:
                # gpt-image-2 支持多参考图
                body["extra_body"] = {"image": references if len(references) > 1 else references[0]}
                logger.info(f"共添加 {len(references)} 张参考图")
            else:
                logger.warning("未能成功加载任何参考图")

        try:
            # 发送请求
            result = await asyncio.to_thread(self._post_request, body)

            if result:
                logger.info("图像生成成功")

                # 保存到文件（如果指定了输出路径）
                if output_path:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(result)
                    logger.info(f"图像已保存到: {output_path}")

                return result
            else:
                logger.error("图像生成失败：返回空数据")
                return None

        except Exception as e:
            logger.error(f"图像生成异常: {e}", exc_info=True)
            return None

    def _post_request(self, body: dict[str, Any]) -> bytes:
        """同步发送 HTTP 请求

        Args:
            body: 请求体

        Returns:
            图像二进制数据
        """
        url = f"{self.base_url}/images/generations"
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8')

        logger.info(f"发送请求到: {url}")
        logger.debug(f"请求体大小: {len(payload)} 字节")

        request = urllib.request.Request(
            url=url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                response_body = response.read()
                logger.info(f"收到响应，状态码: {response.status}")

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', errors='ignore')
            logger.error(f"HTTP 错误 {exc.code}: {detail}")
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except Exception as e:
            logger.error(f"请求失败: {e}")
            raise

        # 解析响应
        data = json.loads(response_body.decode('utf-8'))
        first = (data.get("data") or [{}])[0]

        # 尝试 b64_json
        b64_json = first.get("b64_json")
        if b64_json:
            logger.info("从 b64_json 字段获取图像")
            return base64.b64decode(b64_json)

        # 尝试 URL
        image_url = first.get("url")
        if image_url:
            logger.info(f"从 URL 下载图像: {image_url}")
            with urllib.request.urlopen(str(image_url), timeout=self.timeout) as response:
                return response.read()

        logger.error("响应中未找到图像数据")
        return b""

    @staticmethod
    def _image_to_data_url(path: Path) -> str:
        """将图片文件转换为 data URL

        Args:
            path: 图片文件路径

        Returns:
            data URL 字符串
        """
        suffix = path.suffix.lower().lstrip('.') or 'png'
        mime = 'jpeg' if suffix == 'jpg' else suffix

        try:
            encoded = base64.b64encode(path.read_bytes()).decode('ascii')
            logger.debug(f"图片 {path.name} 编码大小: {len(encoded)} 字符")
            return f"data:image/{mime};base64,{encoded}"
        except Exception as e:
            logger.warning(f"读取图片失败 {path}: {e}")
            return ""


async def test_basic_generation():
    """测试基础生图功能（无参考图）"""
    logger.info("=" * 60)
    logger.info("测试 1: 基础生图（无参考图）")
    logger.info("=" * 60)

    generator = SimpleImageGenerator(
        base_url="https://starport.openainotopen.com/v1",
        api_key="REDACTED_USE_ENV",
        timeout=60,
    )

    prompt = "一个可爱的动漫女孩在樱花树下，春天，阳光明媚，高质量插画"
    output_path = Path("output/test_basic.png")

    result = await generator.generate_image(
        prompt=prompt,
        output_path=output_path,
    )

    if result:
        logger.info(f"✓ 测试通过，图像大小: {len(result)} 字节")
        return True
    else:
        logger.error("✗ 测试失败")
        return False


async def test_with_reference():
    """测试带参考图的生图功能"""
    logger.info("=" * 60)
    logger.info("测试 2: 带参考图生图")
    logger.info("=" * 60)

    generator = SimpleImageGenerator(
        base_url="https://starport.openainotopen.com/v1",
        api_key="REDACTED_USE_ENV",
        timeout=60,
    )

    # 检查参考图目录
    scene_dir = Path("D:/Sakiko/assets/场景")
    character_dir = Path("D:/Sakiko/assets/立绘/小祥")

    reference_images = []

    # 查找第一张场景图
    if scene_dir.exists():
        for img in scene_dir.glob("*.png"):
            reference_images.append(img)
            logger.info(f"使用场景参考图: {img.name}")
            break

    # 查找第一张角色立绘
    if character_dir.exists():
        for img in character_dir.glob("*.png"):
            reference_images.append(img)
            logger.info(f"使用角色参考图: {img.name}")
            break

    if not reference_images:
        logger.warning("未找到参考图，跳过此测试")
        return None

    prompt = "角色站在场景中，自然构图，高质量插画，不要文字，不要水印"
    output_path = Path("output/test_with_ref.png")

    result = await generator.generate_image(
        prompt=prompt,
        reference_images=reference_images,
        output_path=output_path,
    )

    if result:
        logger.info(f"✓ 测试通过，图像大小: {len(result)} 字节")
        return True
    else:
        logger.error("✗ 测试失败")
        return False


async def test_custom_prompt():
    """测试自定义提示词"""
    logger.info("=" * 60)
    logger.info("测试 3: 自定义提示词")
    logger.info("=" * 60)

    generator = SimpleImageGenerator(
        base_url="https://starport.openainotopen.com/v1",
        api_key="REDACTED_USE_ENV",
        timeout=60,
    )

    # 从命令行获取提示词
    print("\n请输入自定义提示词（留空跳过此测试）:")
    custom_prompt = input("> ").strip()

    if not custom_prompt:
        logger.info("跳过自定义提示词测试")
        return None

    output_path = Path("output/test_custom.png")

    result = await generator.generate_image(
        prompt=custom_prompt,
        output_path=output_path,
    )

    if result:
        logger.info(f"✓ 测试通过，图像大小: {len(result)} 字节")
        return True
    else:
        logger.error("✗ 测试失败")
        return False


async def main():
    """主函数"""
    logger.info("图像生成测试脚本启动")
    logger.info(f"Python 版本: {sys.version}")

    # 创建输出目录
    Path("output").mkdir(exist_ok=True)

    results = []

    # 执行测试
    try:
        # 测试 1: 基础生图
        result1 = await test_basic_generation()
        results.append(("基础生图", result1))

        # 等待一下，避免请求过快
        await asyncio.sleep(2)

        # 测试 2: 带参考图
        result2 = await test_with_reference()
        results.append(("带参考图生图", result2))

        # 等待一下
        await asyncio.sleep(2)

        # 测试 3: 自定义提示词
        result3 = await test_custom_prompt()
        if result3 is not None:
            results.append(("自定义提示词", result3))

    except KeyboardInterrupt:
        logger.info("测试被用户中断")
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}", exc_info=True)

    # 输出总结
    logger.info("=" * 60)
    logger.info("测试总结")
    logger.info("=" * 60)

    for name, result in results:
        if result is True:
            logger.info(f"✓ {name}: 成功")
        elif result is False:
            logger.info(f"✗ {name}: 失败")
        else:
            logger.info(f"- {name}: 跳过")

    success_count = sum(1 for _, r in results if r is True)
    total_count = len([r for _, r in results if r is not None])

    logger.info(f"\n通过: {success_count}/{total_count}")

    if success_count == total_count and total_count > 0:
        logger.info("\n🎉 所有测试通过！")
    else:
        logger.info("\n⚠️ 部分测试失败，请检查日志")


if __name__ == "__main__":
    asyncio.run(main())
