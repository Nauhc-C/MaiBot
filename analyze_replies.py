#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import re
import sys

with open('logs/app_20260707_164204.log.jsonl', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 筛选replyer生成成功的日志
replyer_lines = [l for l in lines if '"logger_name"' in l and '"replyer"' in l and '生成成功' in l]

# 取最近50条
recent_lines = replyer_lines[-50:]

replies = []
for line in recent_lines:
    try:
        data = json.loads(line)
        event = data.get('event', '')
        match = re.search(r"文本='(.*?)'", event)
        if match:
            text = match.group(1)
            # 移除[语音消息]标记
            original_text = text
            text = text.replace('[语音消息]', '').strip()
            # 移除[表情包...]标记
            text = re.sub(r'\[表情包:.*?\]', '', text).strip()

            # 统计实际文字长度（移除emoji等）
            text_no_emoji = re.sub(r'[★☆♪♫🎵🎹🎀☕🥰😊🫣✨]', '', text)
            text_no_emoji = re.sub(r'[\U0001F000-\U0001F9FF]', '', text_no_emoji)
            # 移除desuwa等后缀
            text_count = text_no_emoji.replace('desuwa', '').replace('~', '')

            # 按分隔符统计句子数
            # 按换行符分段
            parts = text.split('\n')
            sentences = []
            for part in parts:
                # 每个段落内，按句子分隔符分割
                segs = re.split(r'[。？！~…]', part)
                for seg in segs:
                    seg = seg.strip()
                    if seg and len(seg) > 2:
                        sentences.append(seg)

            timestamp = data.get('timestamp', '')
            replies.append({
                'time': timestamp,
                'text': original_text,
                'clean_text': text,
                'length': len(text_count.strip()),
                'sentences': len(sentences),
                'sentence_list': sentences
            })
    except Exception as e:
        print(f"解析错误: {e}", file=sys.stderr)

print(f"最近{len(replies)}条回复统计：\n")
print(f"{'时间':<15} {'字数':<6} {'句数':<6} 内容预览")
print("-" * 100)

total_chars = 0
total_sentences = 0
for r in replies:
    preview = r['clean_text'][:45] + '...' if len(r['clean_text']) > 45 else r['clean_text']
    preview = preview.replace('\n', ' ')
    print(f"{r['time']:<15} {r['length']:<6} {r['sentences']:<6} {preview}")
    total_chars += r['length']
    total_sentences += r['sentences']

print("\n" + "="*100)
print(f"总计：{len(replies)}条回复")
print(f"平均字数：{total_chars/len(replies):.1f} 字/条")
print(f"平均句数：{total_sentences/len(replies):.1f} 句/条")
print(f"总字数：{total_chars} 字")

# 统计句数分布
sentence_dist = {}
for r in replies:
    count = r['sentences']
    sentence_dist[count] = sentence_dist.get(count, 0) + 1

print(f"\n句数分布：")
for count in sorted(sentence_dist.keys()):
    pct = sentence_dist[count] / len(replies) * 100
    print(f"  {count}句: {sentence_dist[count]:2d}条 ({pct:5.1f}%)")

# 显示典型的例子
print(f"\n=== 1-2句话回复（短回复）===")
short = [r for r in replies if r['sentences'] <= 2]
for r in short[-3:]:
    print(f"\n[{r['time']}] {r['length']}字，{r['sentences']}句")
    print(f"完整内容: {r['clean_text']}")
    for i, s in enumerate(r['sentence_list'], 1):
        print(f"  句{i}: {s}")

print(f"\n=== 3句话回复 ===")
three = [r for r in replies if r['sentences'] == 3]
for r in three[-3:]:
    print(f"\n[{r['time']}] {r['length']}字，{r['sentences']}句")
    print(f"完整内容: {r['clean_text']}")
    for i, s in enumerate(r['sentence_list'], 1):
        print(f"  句{i}: {s}")

print(f"\n=== 较长回复（4句以上）===")
long_replies = [r for r in replies if r['sentences'] >= 4]
for r in long_replies[-3:]:
    print(f"\n[{r['time']}] {r['length']}字，{r['sentences']}句")
    print(f"完整内容: {r['clean_text']}")
    for i, s in enumerate(r['sentence_list'], 1):
        print(f"  句{i}: {s}")
