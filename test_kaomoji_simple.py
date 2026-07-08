#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import io
import re

# Force UTF-8 output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Kaomoji pattern from utils.py
kaomoji_pattern = re.compile(
    r"("
    r"[(\[（【]"  # Left bracket
    r"[^()\[\]（）【】]*?"  # Non-bracket chars (lazy)
    r"[^一-龥a-zA-Z0-9\s]"  # Non-CJK, non-alpha, non-digit, non-space (must have at least one)
    r"[^()\[\]（）【】]*?"  # Non-bracket chars (lazy)
    r"[)\]）】"  # Right bracket
    r"]"
    r")"
    r"|"
    r"([▼▽・ᴥω･﹏^><≧≦￣｀´∀ヮДд︿﹀へ｡ﾟ╥╯╰︶︹•⁄]{2,15})"
)

# Test cases
test_text = "真的好开心desuwa！(˶ᵔᵕᵔ˶)就是这样"
incomplete_text = "真的好开心desuwa！(˶ᵔᵕ"

print("Test 1: Complete kaomoji")
print(f"Text: {test_text}")
matches = kaomoji_pattern.findall(test_text)
print(f"Matches: {matches}")
print()

print("Test 2: Incomplete kaomoji")
print(f"Text: {incomplete_text}")
matches = kaomoji_pattern.findall(incomplete_text)
print(f"Matches: {matches}")
print()

print("Test 3: Character analysis")
special_chars = "˶ᵔᵕᵔ˶"
charset2 = "▼▽・ᴥω･﹏^><≧≦￣｀´∀ヮДд︿﹀へ｡ﾟ╥╯╰︶︹•⁄"
for char in special_chars:
    in_set = char in charset2
    print(f"Char: {char} (U+{ord(char):04X}) - In charset2: {in_set}")
