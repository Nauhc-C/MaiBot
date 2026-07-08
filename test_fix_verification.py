#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
import re

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 修复后的颜文字模式
kaomoji_pattern_fixed = re.compile(
    r"("
    r"[(\[（【]"  # 左括号
    r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
    r"[^一-龥a-zA-Z0-9]"  # 非中文、非英文、非数字字符（必须包含至少一个）- 移除了\s
    r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
    r"[)\]）】]"  # 右括号
    r")"
    r"|"
    r"([▼▽・ᴥω･﹏^><≧≦￣｀´∀ヮДд︿﹀へ｡ﾟ╥╯╰︶︹•⁄˶ᵔᵕ]{2,15})"
)

# 修复前的颜文字模式（原始版本）
kaomoji_pattern_old = re.compile(
    r"("
    r"[(\[（【]"  # 左括号
    r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
    r"[^一-龥a-zA-Z0-9\s]"  # 非中文、非英文、非数字、非空格字符（必须包含至少一个）
    r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
    r"[)\]）】]"  # 右括号
    r")"
    r"|"
    r"([▼▽・ᴥω･﹏^><≧≦￣｀´∀ヮДд︿﹀へ｡ﾟ╥╯╰︶︹•⁄]{2,15})"
)

# 测试用例
test_cases = [
    "真的好开心desuwa！(˶ᵔ ᵕ ᵔ˶)",  # 带空格的颜文字（真实案例）
    "真的好开心desuwa！(˶ᵔᵕᵔ˶)",   # 不带空格的颜文字
    "(^_^)",
    "测试(˶ᵔ ᵕ ᵔ˶)表情",
]

print("=" * 80)
print("颜文字识别修复测试")
print("=" * 80)

for i, text in enumerate(test_cases, 1):
    print(f"\n【测试 {i}】文本: {text}")

    # 测试修复前的模式
    matches_old = kaomoji_pattern_old.findall(text)
    print(f"  修复前: ", end="")
    if matches_old:
        for match in matches_old:
            kaomoji = match[0] or match[1]
            print(f"✓ 识别到 {kaomoji!r}")
    else:
        print("✗ 未识别")

    # 测试修复后的模式
    matches_fixed = kaomoji_pattern_fixed.findall(text)
    print(f"  修复后: ", end="")
    if matches_fixed:
        for match in matches_fixed:
            kaomoji = match[0] or match[1]
            print(f"✓ 识别到 {kaomoji!r}")
    else:
        print("✗ 未识别")

print("\n" + "=" * 80)
print("完整流程测试（修复后）")
print("=" * 80)

def protect_kaomoji_fixed(sentence):
    """修复后的保护函数"""
    kaomoji_matches = kaomoji_pattern_fixed.findall(sentence)
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

# 测试真实案例
real_case = "真的好开心desuwa！(˶ᵔ ᵕ ᵔ˶)"
print(f"\n真实案例: {real_case}")

protected, mapping = protect_kaomoji_fixed(real_case)
print(f"保护后: {protected}")
print(f"映射表: {mapping}")

if mapping:
    print("✓ 修复成功！颜文字被正确识别和保护")
else:
    print("✗ 修复失败，颜文字仍未被识别")
