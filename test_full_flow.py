#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
import re
import random

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def protect_kaomoji(sentence):
    """从 utils.py 复制的函数"""
    kaomoji_pattern = re.compile(
        r"("
        r"[(\[（【]"  # 左括号
        r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
        r"[^一-龥a-zA-Z0-9\s]"  # 非中文、非英文、非数字、非空格字符（必须包含至少一个）
        r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
        r"[)\]）】"  # 右括号
        r"]"
        r")"
        r"|"
        r"([▼▽・ᴥω･﹏^><≧≦￣｀´∀ヮДд︿﹀へ｡ﾟ╥╯╰︶︹•⁄]{2,15})"
    )

    kaomoji_matches = kaomoji_pattern.findall(sentence)
    placeholder_to_kaomoji = {}

    for match in kaomoji_matches:
        kaomoji = match[0] or match[1]
        if kaomoji.startswith("[表情包") and kaomoji.endswith("]"):
            continue
        idx = len(placeholder_to_kaomoji)
        placeholder = f"__KAOMOJI_{idx}__"
        sentence = sentence.replace(kaomoji, placeholder, 1)
        placeholder_to_kaomoji[placeholder] = kaomoji

    return sentence, placeholder_to_kaomoji

def is_english_letter(char):
    """检查字符是否为英文字母"""
    return "a" <= char.lower() <= "z"

def split_into_sentences_w_remove_punctuation(text):
    """简化版分句函数，测试关键逻辑"""
    # 预处理
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"\n\s*([，,。;\s])", r"\n\1", text)
    text = re.sub(r"([，,。;\s])\s*\n", r"\1\n", text)

    len_text = len(text)
    if len_text < 3:
        return list(text) if random.random() < 0.01 else [text]

    # 定义分隔符
    separators = {"，", ",", " ", "。", ";", "\n"}
    segments = []
    current_segment = ""

    # 1. 分割成 (内容, 分隔符) 元组
    i = 0
    while i < len(text):
        char = text[i]
        if char in separators:
            can_split = True

            # 检查空格的特殊情况
            if char == " " and i > 0 and i < len(text) - 1:
                prev_char = text[i - 1]
                next_char = text[i + 1]
                prev_is_alnum = prev_char.isdigit() or is_english_letter(prev_char)
                next_is_alnum = next_char.isdigit() or is_english_letter(next_char)
                if prev_is_alnum and next_is_alnum:
                    can_split = False

            if can_split:
                if current_segment:
                    segments.append((current_segment, char))
                elif char in {" ", "\n"}:
                    segments.append(("", char))
                current_segment = ""
            else:
                current_segment += char
        else:
            current_segment += char
        i += 1

    # 添加最后一个段
    if current_segment:
        segments.append((current_segment, ""))

    # 过滤空段
    segments = [(content, sep) for content, sep in segments if content or sep]

    if not segments:
        return [text] if text else []

    # 2. 概率合并（简化版，不做合并）
    final_sentences = [content for content, sep in segments if content]

    # 清理空字符串
    final_sentences = [s for s in final_sentences if s.strip()]

    return final_sentences

# 测试完整流程
test_cases = [
    ("真的好开心desuwa！(˶ᵔᵕᵔ˶)就是这样", "完整颜文字"),
    ("真的好开心desuwa！(˶ᵔᵕ", "不完整颜文字"),
    ("真的好开心desuwa！(˶ᵔᵕ就断开的现象没有吧表情发完", "用户报告的问题"),
]

print("=" * 80)
print("完整流程测试：protect_kaomoji + split_into_sentences")
print("=" * 80)

for text, desc in test_cases:
    print(f"\n【{desc}】")
    print(f"原文: {text}")
    print(f"长度: {len(text)} 字符")

    # 步骤1: 保护颜文字
    protected, mapping = protect_kaomoji(text)
    print(f"\n保护后: {protected}")
    print(f"映射表: {mapping}")

    # 步骤2: 分句
    sentences = split_into_sentences_w_remove_punctuation(protected)
    print(f"\n分句结果 ({len(sentences)} 句):")
    for i, sent in enumerate(sentences, 1):
        print(f"  {i}. {sent}")

    # 步骤3: 恢复
    if mapping:
        for placeholder, kaomoji in mapping.items():
            sentences = [s.replace(placeholder, kaomoji) for s in sentences]

    print(f"\n最终结果:")
    for i, sent in enumerate(sentences, 1):
        print(f"  {i}. {sent}")

    print("-" * 80)
