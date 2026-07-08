"""测试 right.codes gpt-image-2 API 的图像生成功能"""

import asyncio
import json
import sys
import urllib.request
from pathlib import Path


class RightCodesImageGenerator:
    """right.codes API 测试生成器"""

    def __init__(self):
        self.base_url = "https://www.right.codes/draw"
        self.api_key = "REDACTED_USE_ENV"
        self.model = "gpt-image-2"
        self.timeout = 120
        self.poll_interval = 2

    def submit_task(self, prompt: str) -> str | None:
        """提交生图任务"""
        url = f"{self.base_url}/v1/images/generations"
        body = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
            "size": "1:1",
            "async": True,
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")

        print(f"提交任务到: {url}")
        print(f"提示词: {prompt}")

        request = urllib.request.Request(
            url=url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                response_body = response.read()
                print(f"提交成功，状态码: {response.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            print(f"提交失败 HTTP {exc.code}: {detail}")
            return None

        data = json.loads(response_body.decode("utf-8"))
        task_id = data.get("task_id")
        print(f"task_id: {task_id}")
        return task_id

    async def poll_task_result(self, task_id: str) -> str | None:
        """轮询任务结果"""
        print(f"\n开始轮询任务: {task_id}")
        start_time = asyncio.get_event_loop().time()
        attempt = 0

        while True:
            attempt += 1
            elapsed = asyncio.get_event_loop().time() - start_time

            if elapsed > self.timeout:
                print(f"超时 ({elapsed:.1f}s)")
                return None

            result = await asyncio.to_thread(self.query_task, task_id)

            if result is None:
                return None

            status = result.get("status", "")
            progress = result.get("progress", 0)

            print(f"[{attempt}] 状态: {status}, 进度: {progress}%, 耗时: {elapsed:.1f}s")

            if status == "failed":
                error_msg = result.get("error", {}).get("message", "未知错误")
                print(f"任务失败: {error_msg}")
                return None

            if status in ["queued", "in_progress"]:
                await asyncio.sleep(self.poll_interval)
                continue

            # 任务完成
            if "data" in result:
                data_list = result.get("data", [])
                if data_list and len(data_list) > 0:
                    image_url = data_list[0].get("url")
                    print(f"\n生图完成！")
                    print(f"图片 URL: {image_url}")
                    return image_url

            print(f"响应格式异常: {result}")
            return None

    def query_task(self, task_id: str) -> dict | None:
        """查询任务状态"""
        url = f"https://www.right.codes/v1/tasks/{task_id}"

        request = urllib.request.Request(
            url=url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                response_body = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            print(f"查询失败 HTTP {exc.code}: {detail}")
            return None

        return json.loads(response_body.decode("utf-8"))

    def download_image(self, image_url: str, output_path: Path) -> bool:
        """下载图片"""
        print(f"\n下载图片到: {output_path}")

        request = urllib.request.Request(
            url=image_url,
            headers={"User-Agent": "Mozilla/5.0"},
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                image_data = response.read()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(image_data)

            print(f"下载成功，大小: {len(image_data)} 字节 ({len(image_data) // 1024} KB)")
            return True

        except Exception as e:
            print(f"下载失败: {e}")
            return False


async def main():
    """主函数"""
    print("=" * 60)
    print("right.codes gpt-image-2 API 测试")
    print("=" * 60)

    generator = RightCodesImageGenerator()

    # 测试提示词
    prompt = "一只可爱的橘猫在窗边晒太阳，温暖的阳光，高质量插画"

    print(f"\n{'='*60}")
    print("步骤 1: 提交生图任务")
    print(f"{'='*60}\n")

    task_id = generator.submit_task(prompt)

    if not task_id:
        print("\n❌ 提交任务失败")
        return

    print(f"\n{'='*60}")
    print("步骤 2: 轮询任务状态")
    print(f"{'='*60}")

    image_url = await generator.poll_task_result(task_id)

    if not image_url:
        print("\n❌ 获取结果失败")
        return

    print(f"\n{'='*60}")
    print("步骤 3: 下载图片")
    print(f"{'='*60}")

    output_path = Path("output/test_rightcodes.png")
    success = generator.download_image(image_url, output_path)

    print(f"\n{'='*60}")
    if success:
        print("✅ 测试成功！")
        print(f"图片已保存: {output_path}")
    else:
        print("❌ 测试失败")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
