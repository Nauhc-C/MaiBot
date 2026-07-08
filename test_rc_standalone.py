"""独立测试 right.codes API（不依赖 MaiBot）"""
import asyncio
import json
import urllib.request
from pathlib import Path


async def test_rightcodes():
    """测试 right.codes gpt-image-2 API"""
    print("测试 right.codes gpt-image-2 API")
    print("=" * 60)

    base_url = "https://www.right.codes/draw"
    api_key = "REDACTED_USE_ENV"
    model = "gpt-image-2"

    # 步骤1: 提交任务
    print("\n步骤 1: 提交生图任务")
    url = f"{base_url}/v1/images/generations"
    body = {
        "model": model,
        "prompt": "一只可爱的小猫在阳光下",
        "n": 1,
        "size": "1:1",
        "async": True,
    }

    request = urllib.request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
        task_id = data.get("task_id")
        print(f"任务已提交: {task_id}")

    # 步骤2: 轮询任务
    print("\n步骤 2: 轮询任务状态")
    for i in range(60):  # 最多轮询60次（120秒）
        await asyncio.sleep(2)

        url = f"https://www.right.codes/v1/tasks/{task_id}"
        request = urllib.request.Request(
            url=url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
        )

        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))

        status = result.get("status", "")
        progress = result.get("progress", 0)
        print(f"[{i+1}] 状态: {status}, 进度: {progress}%")

        if status == "failed":
            print(f"失败: {result.get('error')}")
            return

        if "data" in result:
            image_url = result["data"][0]["url"]
            print(f"\n生成完成! URL: {image_url}")

            # 步骤3: 下载图片
            print("\n步骤 3: 下载图片")
            request = urllib.request.Request(
                url=image_url,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                image_data = response.read()

            output = Path("output/test_rc_success.png")
            output.parent.mkdir(exist_ok=True)
            output.write_bytes(image_data)

            print(f"成功! 大小: {len(image_data)} 字节")
            print(f"已保存到: {output}")
            return

    print("\n超时!")


if __name__ == "__main__":
    asyncio.run(test_rightcodes())
