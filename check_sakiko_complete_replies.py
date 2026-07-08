#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查 Sakiko 最近 12 小时的完整回复，统计平均回复长度（字数，自动去除 desuwa）"""

from datetime import datetime, timedelta
import re
import sys
import io
from pathlib import Path

# 设置标准输出为 UTF-8 编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 添加项目根目录到 sys.path
project_root = Path(__file__).parent / "project" / "MaiBot"
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
    """统计文本字数（所有非空白字符）"""
    if not text:
        return 0
    # 移除多余的空白字符
    text = text.strip()
    text = re.sub(r'\s+', '', text)
    return len(text)


def group_messages_into_replies(messages, max_gap_seconds=10):
    """
    将消息按时间戳分组为完整回复
    如果两条消息的时间间隔小于 max_gap_seconds 秒，则认为它们属于同一次回复
    """
    if not messages:
        return []

    replies = []
    current_reply = []
    last_timestamp = None

    for msg in messages:
        if last_timestamp is None:
            # 第一条消息
            current_reply = [msg]
            last_timestamp = msg.timestamp
        else:
            # 计算时间差
            time_diff = (msg.timestamp - last_timestamp).total_seconds()

            if time_diff <= max_gap_seconds:
                # 属于同一次回复
                current_reply.append(msg)
            else:
                # 新的回复开始
                if current_reply:
                    replies.append(current_reply)
                current_reply = [msg]

            last_timestamp = msg.timestamp

    # 添加最后一组
    if current_reply:
        replies.append(current_reply)

    return replies


def merge_reply_texts(reply_messages):
    """合并一次回复中所有消息的文本"""
    texts = []
    for msg in reply_messages:
        if msg.processed_plain_text and msg.processed_plain_text.strip():
            texts.append(msg.processed_plain_text.strip())
    return ' '.join(texts)


def main():
    # 配置
    sakiko_user_id = "BOT_ACCOUNT_ID"  # Sakiko 的 QQ 账号
    hours_ago = 12
    max_gap_seconds = 10  # 消息间隔小于此秒数视为同一次回复

    # 计算时间范围
    now = datetime.now()
    start_time = now - timedelta(hours=hours_ago)

    print(f"查询时间范围: {start_time.strftime('%Y-%m-%d %H:%M:%S')} 到 {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"查询用户: {sakiko_user_id}")
    print(f"分组间隔: {max_gap_seconds} 秒\n")

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

    # 按时间戳分组为完整回复
    replies = group_messages_into_replies(messages, max_gap_seconds)

    print(f"合并为 {len(replies)} 次完整回复\n")

    # 统计每次完整回复的长度
    total_length = 0
    valid_replies = 0
    reply_details = []

    for i, reply_messages in enumerate(replies):
        # 合并文本
        full_text = merge_reply_texts(reply_messages)

        if not full_text:
            continue

        # 去除 desuwa
        text_cleaned = remove_desuwa(full_text)

        # 统计字数
        length = count_text_length(text_cleaned)

        if length > 0:
            total_length += length
            valid_replies += 1

            # 记录详情（只显示前几条）
            if valid_replies <= 15:
                first_msg = reply_messages[0]
                timestamp = first_msg.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                preview_text = full_text.encode('utf-8', errors='ignore').decode('utf-8')
                preview = preview_text[:80] + '...' if len(preview_text) > 80 else preview_text
                reply_details.append({
                    'timestamp': timestamp,
                    'message_count': len(reply_messages),
                    'preview': preview,
                    'length': length
                })

    # 显示前几次回复的详情
    print("=" * 80)
    print("回复示例（前15次）:")
    print("=" * 80)
    for i, detail in enumerate(reply_details, 1):
        print(f"\n回复 {i}:")
        print(f"  时间: {detail['timestamp']}")
        print(f"  分句数: {detail['message_count']}")
        print(f"  内容预览: {detail['preview']}")
        print(f"  字数: {detail['length']}")

    # 计算并显示统计结果
    print("\n" + "=" * 80)
    print("统计结果:")
    print("=" * 80)
    print(f"总消息数（分句后）: {len(messages)}")
    print(f"总回复次数（合并后）: {len(replies)}")
    print(f"有效回复数（非空）: {valid_replies}")
    print(f"总字数: {total_length}")

    if valid_replies > 0:
        average_length = total_length / valid_replies
        print(f"平均回复长度: {average_length:.2f} 字")
    else:
        print("平均回复长度: 无有效回复")


if __name__ == "__main__":
    main()
