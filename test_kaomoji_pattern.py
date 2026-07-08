#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""独立测试颜文字识别模式"""

import re

# 从 utils.py 复制的颜文字模式
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

# 测试用例
test_cases = [
    "真的好开心desuwa！(˶ᵔᵕᵔ˶)就是这样",
    "(˶ᵔᵕᵔ˶)",
    "(^_^)",
    "(˶ᵔᵕ",  # 不完整
    "测试˶ᵔᵕᵔ˶内容",  # 没有括号
    "(abc)",  # 纯英文不应该匹配
    "(123)",  # 纯数字不应该匹配
]

print("=" * 80)
print("测试颜文字正则表达式匹配")
print("=" * 80)

for i, text in enumerate(test_cases, 1):
    print(f"\n【测试 {i}】文本: {text!r}")

    # 查找所有匹配
    matches = kaomoji_pattern.findall(text)

    if matches:
        print(f"  ✓ 找到 {len(matches)} 个匹配:")
        for match in matches:
            kaomoji = match[0] or match[1]
            print(f"    - {kaomoji!r}")

            # 显示每个字符的 Unicode
            print(f"      字符详情:", end=" ")
            for char in kaomoji:
                print(f"{char}(U+{ord(char):04X})", end=" ")
            print()
    else:
        print(f"  ✗ 没有匹配")

print("\n" + "=" * 80)
print("分析特殊字符")
print("=" * 80)

special_chars = "˶ᵔᵕᵔ˶"
print(f"\n特殊字符串: {special_chars!r}")
print("字符详情:")
for char in special_chars:
    # 检查字符是否在第二部分的字符集中
    in_set2 = char in "▼▽・ᴥω･﹏^><≧≦￣｀´∀ヮДд︿﹀へ｡ﾟ╥╯╰︶︹•⁄"
    # 检查是否是中文、英文、数字或空格
    is_excluded = (
        '一' <= char <= '鿿' or  # 中文
        'a' <= char.lower() <= 'z' or  # 英文
        char.isdigit() or  # 数字
        char.isspace()  # 空格
    )
    print(f"  {char} (U+{ord(char):04X}) - 在字符集2: {in_set2}, 被排除: {is_excluded}")
