#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 Sakiko 最近 12 小时的发言，统计平均回复长度（字数，自动去除 desuwa）"""

from datetime import datetime, timedelta
import re
import sys
import io
from pathlib import Path

# 设置标准输出为 UTF-8 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from src.common.message_repository import find_messages


def remove_desuwa(text: str) -> str:
    """去除文本中的 desuwa"""
    if not text:
        return text
    # 去除 desuwa 及其变体（不区分大小写）
    text = re.sub(r'desuwa', '', text, flags=re.IGNORECASE)
    return text


def count_text_length(text: str) -> int:
    """统计文本字数（中文字符和英文单词）"""
    if not text:
        return 0

    # 简化：直接统计所有非空白字符
    text = text.strip()
    # 移除多余的空白字符
    text = re.sub(r'\s+', '', text)
    return len(text)


def main():
    # 配置
    sakiko_user_id = "BOT_ACCOUNT_ID"  # Sakiko 的 QQ 账号
    hours_ago = 12

    # 计算时间范围
    now = datetime.now()
    start_time = now - timedelta(hours=hours_ago)

    print(f"查询时间范围: {start_time.strftime('%Y-%m-%d %H:%M:%S')} 到 {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"查询用户: {sakiko_user_id}\n")

    # 查询消息
    messages = find_messages(
        user_id=sakiko_user_id,
        start_time=start_time.timestamp(),
        end_time=now.timestamp(),
        filter_command=True,  # 过滤掉命令消息
    )

    print(f"找到 {len(messages)} 条消息\n")

    if not messages:
        print("没有找到符合条件的消息")
        return

    # 统计每条消息的长度
    total_length = 0
    valid_messages = 0
    message_details = []

    for msg in messages:
        text = msg.processed_plain_text
        if not text or not text.strip():
            continue

        # 去除 desuwa
        text_cleaned = remove_desuwa(text)

        # 统计字数
        length = count_text_length(text_cleaned)

        if length > 0:
            total_length += length
            valid_messages += 1

            # 记录详情（只显示前几条）
            if valid_messages <= 10:
                timestamp = msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                # 移除可能导致编码问题的特殊字符
                preview_text = text.encode('utf-8', errors='ignore').decode('utf-8')
                preview = preview_text[:50] + '...' if len(preview_text) > 50 else preview_text
                message_details.append({
                    'timestamp': timestamp,
                    'preview': preview,
                    'original_length': count_text_length(remove_desuwa(text) if text else ""),
                    'cleaned_length': length
                })

    # 显示前几条消息的详情
    print("=" * 60)
    print("消息示例（前10条）:")
    print("=" * 60)
    for i, detail in enumerate(message_details, 1):
        print(f"\n消息 {i}:")
        print(f"  时间: {detail['timestamp']}")
        print(f"  内容预览: {detail['preview']}")
        print(f"  字数: {detail['cleaned_length']}")

    # 计算并显示统计结果
    print("\n" + "=" * 60)
    print("统计结果:")
    print("=" * 60)
    print(f"总消息数: {len(messages)}")
    print(f"有效消息数（非空）: {valid_messages}")
    print(f"总字数: {total_length}")

    if valid_messages > 0:
        average_length = total_length / valid_messages
        print(f"平均回复长度: {average_length:.2f} 字")
    else:
        print("平均回复长度: 无有效消息")


if __name__ == "__main__":
    main()
