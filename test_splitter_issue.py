#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试分句器在处理特殊表情时的行为"""

import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.chat.utils.utils import split_into_sentences_w_remove_punctuation, protect_kaomoji, recover_kaomoji

# 测试用例
test_cases = [
    "真的好开心desuwa！(˶ᵔᵕᵔ˶)就是这样没有断开吧",
    "真的好开心desuwa！(˶ᵔᵕᵔ˶)",
    "测试(˶ᵔᵕᵔ˶)表情",
    "哈哈(^_^)开心",
    "真的好开心desuwa！(˶ᵔᵕ",  # 不完整的表情
]

print("=" * 80)
print("测试分句器处理特殊表情符号")
print("=" * 80)

for i, text in enumerate(test_cases, 1):
    print(f"\n【测试 {i}】")
    print(f"原文: {text}")
    print(f"原文长度: {len(text)} 字符")

    # 测试颜文字保护
    protected_text, kaomoji_mapping = protect_kaomoji(text)
    print(f"\n保护后: {protected_text}")
    print(f"颜文字映射: {kaomoji_mapping}")

    # 测试分句
    sentences = split_into_sentences_w_remove_punctuation(text)
    print(f"\n分句结果 (共 {len(sentences)} 句):")
    for j, sentence in enumerate(sentences, 1):
        print(f"  {j}. [{len(sentence)}字符] {sentence!r}")

    # 测试恢复
    if kaomoji_mapping:
        recovered = recover_kaomoji(sentences, kaomoji_mapping)
        print(f"\n恢复后:")
        for j, sentence in enumerate(recovered, 1):
            print(f"  {j}. {sentence!r}")

    print("-" * 80)
