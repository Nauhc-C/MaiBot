"""使用 Gemini Flash Image API 的图像生成测试脚本

当 starport gpt-image-2 不可用时，使用 ikun 的 gemini-flash-image 作为备用。
"""

import asyncio
import base64
import json
import logging
import re
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
        logging.FileHandler('image_gen_gemini_test.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class GeminiImageGenerator:
    """Gemini Flash Image 生成器（使用 chat/completions API）"""

    def __init__(self, base_url: str, api_key: str, timeout: int = 90):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout

    async def generate_image(
        self,
        prompt: str,
        reference_images: list[Path] | None = None,
        output_path: Path | None = None,
    ) -> bytes | None:
        """生成图像"""
        logger.info(f"开始生成图像，提示词: {prompt}")

        # 构建请求内容
        content_parts = [{"type": "text", "text": f"Draw: {prompt}"}]

        # 添加参考图
        if reference_images:
            for idx, img_path in enumerate(reference_images, 1):
                if not img_path.exists():
                    logger.warning(f"参考图 #{idx} 不存在: {img_path}")
                    continue

                data_url = self._image_to_data_url(img_path)
                if data_url:
                    content_parts.append({
                        "type": "image_url",
                        "image_url": {"url": data_url}
                    })
                    logger.info(f"添加参考图 #{idx}: {img_path.name}")

        # 构建请求体
        body = {
            "model": "gemini-3.1-flash-image-preview",
            "messages": [{"role": "user", "content": content_parts}],
            "modalities": ["text", "image"],
            "max_tokens": 4096,
        }

        try:
            result = await asyncio.to_thread(self._post_request, body)

            if result:
                logger.info("图像生成成功")

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
        """发送 chat/completions 请求"""
        url = f"{self.base_url}/chat/completions"
        payload = json.dumps(body, ensure_ascii=False).encode('utf-8')

        logger.info(f"发送请求到: {url}")
        logger.debug(f"请求体大小: {len(payload)} 字节")

        request = urllib.request.Request(
            url=url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json",
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

        # 解析响应
        data = json.loads(response_body.decode('utf-8'))
        message = (data.get("choices") or [{}])[0].get("message") or {}
        raw_content = message.get("content") or ""

        # 情形1: content 是列表，包含 image_url 类型
        if isinstance(raw_content, list):
            for part in raw_content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    durl = (part.get("image_url") or {}).get("url", "")
                    if "base64," in durl:
                        logger.info("从结构化 image_url 提取图像")
                        return base64.b64decode(durl.split("base64,", 1)[1])

        # 情形2: content 是文本，图片以 markdown 格式内嵌
        if isinstance(raw_content, str):
            m = re.search(r"data:image/[^;]+;base64,([A-Za-z0-9+/=]{100,})", raw_content)
            if m:
                logger.info("从 markdown data URL 提取图像")
                return base64.b64decode(m.group(1))

        logger.error(f"响应中未找到图像数据，content 类型: {type(raw_content)}")
        return b""

    @staticmethod
    def _image_to_data_url(path: Path) -> str:
        """将图片文件转换为 data URL"""
        suffix = path.suffix.lower().lstrip('.') or 'png'
        mime = 'jpeg' if suffix in ('jpg', 'jpeg') else suffix

        try:
            encoded = base64.b64encode(path.read_bytes()).decode('ascii')
            logger.debug(f"图片 {path.name} 编码大小: {len(encoded)} 字符")
            return f"data:image/{mime};base64,{encoded}"
        except Exception as e:
            logger.warning(f"读取图片失败 {path}: {e}")
            return ""


async def test_basic_generation():
    """测试基础生图"""
    logger.info("=" * 60)
    logger.info("测试 1: 基础生图（无参考图）- Gemini")
    logger.info("=" * 60)

    generator = GeminiImageGenerator(
        base_url="https://api.ikuncode.cc/v1",
        api_key="REDACTED_USE_ENV",
        timeout=90,
    )

    prompt = "一个可爱的动漫女孩在樱花树下，春天，阳光明媚，高质量插画"
    output_path = Path("output/test_gemini_basic.png")

    result = await generator.generate_image(prompt=prompt, output_path=output_path)

    if result:
        logger.info(f"[OK] 测试通过，图像大小: {len(result)} 字节")
        return True
    else:
        logger.error("[FAIL] 测试失败")
        return False


async def test_with_reference():
    """测试带参考图的生图"""
    logger.info("=" * 60)
    logger.info("测试 2: 带参考图生图 - Gemini")
    logger.info("=" * 60)

    generator = GeminiImageGenerator(
        base_url="https://api.ikuncode.cc/v1",
        api_key="REDACTED_USE_ENV",
        timeout=90,
    )

    scene_dir = Path("D:/Sakiko/assets/场景")
    character_dir = Path("D:/Sakiko/assets/立绘/小祥")

    reference_images = []

    # 查找场景图
    if scene_dir.exists():
        for img in scene_dir.glob("*.*"):
            if img.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                reference_images.append(img)
                logger.info(f"使用场景参考图: {img.name}")
                break

    # 查找角色立绘
    if character_dir.exists():
        for img in character_dir.glob("*.*"):
            if img.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
                reference_images.append(img)
                logger.info(f"使用角色参考图: {img.name}")
                break

    if not reference_images:
        logger.warning("未找到参考图，跳过此测试")
        return None

    prompt = "角色站在场景中，自然构图，高质量插画，不要文字，不要水印"
    output_path = Path("output/test_gemini_with_ref.png")

    result = await generator.generate_image(
        prompt=prompt,
        reference_images=reference_images,
        output_path=output_path,
    )

    if result:
        logger.info(f"[OK] 测试通过，图像大小: {len(result)} 字节")
        return True
    else:
        logger.error("[FAIL] 测试失败")
        return False


async def main():
    """主函数"""
    logger.info("Gemini Flash Image 测试脚本启动")
    logger.info(f"Python 版本: {sys.version}")

    Path("output").mkdir(exist_ok=True)

    results = []

    try:
        # 测试 1
        result1 = await test_basic_generation()
        results.append(("Gemini 基础生图", result1))

        await asyncio.sleep(2)

        # 测试 2
        result2 = await test_with_reference()
        results.append(("Gemini 带参考图", result2))

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
            logger.info(f"[OK] {name}: 成功")
        elif result is False:
            logger.info(f"[FAIL] {name}: 失败")
        else:
            logger.info(f"[SKIP] {name}: 跳过")

    success_count = sum(1 for _, r in results if r is True)
    total_count = len([r for _, r in results if r is not None])

    logger.info(f"\n通过: {success_count}/{total_count}")

    if success_count == total_count and total_count > 0:
        logger.info("\n所有测试通过！")
    else:
        logger.info("\n部分测试失败，请检查日志")


if __name__ == "__main__":
    asyncio.run(main())
