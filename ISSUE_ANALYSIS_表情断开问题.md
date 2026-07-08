# 表情符号断开问题分析报告

## 问题描述

用户报告：最近的发言中出现了文本被断开的现象，例如：
```
"真的好开心desuwa！(˶ᵔᵕ就断开的现象没有吧表情发完"
```

预期应该是：
```
"真的好开心desuwa！(˶ᵔᵕᵔ˶)就是这样没有断开吧"
```

表情符号 `(˶ᵔᵕᵔ˶)` 在中间被截断了。

## 问题定位

### 测试结果

通过测试 `src/chat/utils/utils.py` 中的分句器和颜文字保护机制，我发现：

1. **完整的颜文字能被正确识别和保护**
   - 输入：`"真的好开心desuwa！(˶ᵔᵕᵔ˶)就是这样"`
   - 颜文字 `(˶ᵔᵕᵔ˶)` 被识别并替换为占位符
   - 分句后能正确恢复

2. **不完整的颜文字无法被识别**
   - 输入：`"真的好开心desuwa！(˶ᵔᵕ"`
   - 因为缺少右括号 `)`，不会被识别为颜文字
   - 分句器直接处理原始文本

3. **用户报告的文本中，表情已经是不完整的**
   - `(˶ᵔᵕ` 后面没有 `)`，无法被识别为颜文字

### 结论

**问题不在分句器，而在生成阶段。**

文本在以下某个环节被截断：
1. **LLM 生成回复时就不完整**（最可能）
2. **rich reply checker 的输出被截断**
3. **某个字符串处理环节截断了文本**

## 可能原因

### 1. LLM Token 限制

查看代码发现：
- `src/config/default_model_config.py` 中配置了各任务的 `max_tokens`
- replyer 任务默认 `max_tokens: 4096` 或 `8192`
- 如果 LLM 生成到 token 限制，会被强制截断

### 2. Rich Reply Checker 问题

如果启用了 `experimental.enable_rich_reply`，回复会经过两次生成：
1. 第一次：replyer 生成原始回复
2. 第二次：rich reply checker 检查并可能改写

在 `src/maisaka/builtin_tool/reply.py:289-295`：
```python
if rich_reply_enabled:
    reply_sequences = await tool_ctx.post_process_rich_reply_message_sequences_async(
        reply_text,
        original_reply_text_for_rich_output,
    )
```

如果 checker 输出格式有问题，可能导致文本被截断。

### 3. 特殊字符编码问题

颜文字中的特殊字符（如 `˶ᵔᵕ`）是 Unicode 字符：
- `˶` (U+02F6) - MODIFIER LETTER SMALL CAPITAL TURNED R
- `ᵔ` (U+1D54) - MODIFIER LETTER SMALL TURNED AE  
- `ᵕ` (U+1D55) - MODIFIER LETTER SMALL TURNED OPEN E

某些 LLM 或编码环节可能对这些字符处理不当。

## 调试建议

### 1. 检查日志

查看最近的日志文件，搜索关键词：
```bash
cd D:/Sakiko/project/MaiBot
grep -r "好开心desuwa" logs/ --include="*.log"
grep -r "˶ᵔᵕ" logs/ --include="*.log"
```

查看：
- replyer 原始输出是什么
- rich reply checker 的输出是什么
- 在哪个环节文本变得不完整

### 2. 检查配置

查看 `config/bot_config.toml` 和 `config/model_config.toml`：

```bash
grep -E "enable_rich_reply|max_tokens" config/*.toml
```

- 如果 `enable_rich_reply = true`，可能是 checker 问题
- 检查 replyer 任务的 `max_tokens` 设置

### 3. 复现问题

尝试在相同场景下触发该问题，观察：
1. 使用相同的提示词
2. 在相同长度的上下文下
3. 生成包含特殊表情的回复

### 4. 临时禁用 Rich Reply

在 `config/bot_config.toml` 中：
```toml
[experimental]
enable_rich_reply = false
```

如果问题消失，说明是 rich reply checker 导致的。

## 修复方案

### 方案 1: 增加 max_tokens

如果是 token 限制问题，在 `config/model_config.toml` 中增加 replyer 的 `max_tokens`：

```toml
[replyer]
max_tokens = 8192  # 或更大
```

### 方案 2: 改进颜文字保护模式

当前 `protect_kaomoji` 函数的正则表达式不包含 `˶ᵔᵕ` 这些字符。

修改 `src/chat/utils/utils.py:667-678` 的颜文字模式，增加这些 Unicode 修饰字符：

```python
kaomoji_pattern = re.compile(
    r"("
    r"[(\[（【]"  # 左括号
    r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
    r"[^一-龥a-zA-Z0-9\s]"  # 非中文、非英文、非数字、非空格字符（必须包含至少一个）
    r"[^()\[\]（）【】]*?"  # 非括号字符（惰性匹配）
    r"[)\]）】]"  # 右括号  # 注意：修复了原始代码中多余的 ]
    r")"
    r"|"
    r"([▼▽・ᴥω･﹏^><≧≦￣｀´∀ヮДд︿﹀へ｡ﾟ╥╯╰︶︹•⁄˶ᵔᵕ]{2,15})"  # 添加 ˶ᵔᵕ
)
```

**但这只能保护完整的表情，无法解决生成时就不完整的问题。**

### 方案 3: 后处理检测不完整表情

在 `process_llm_response` 或 `post_process_reply_text` 中，检测不完整的括号表情并修复：

```python
def fix_incomplete_kaomoji(text: str) -> str:
    """检测并修复不完整的颜文字"""
    import re
    
    # 检测未闭合的左括号后跟特殊字符
    incomplete_pattern = r'\([^\)]*[˶ᵔᵕᵖᶦᵃ]+[^\)]*$'
    
    if re.search(incomplete_pattern, text):
        logger.warning(f"检测到不完整的颜文字，已移除: {text}")
        # 移除不完整的部分
        text = re.sub(incomplete_pattern, '', text)
    
    return text
```

### 方案 4: 在 Rich Reply Checker 中处理

如果问题出在 rich reply checker，可以在 `src/maisaka/builtin_tool/context.py` 的 `post_process_rich_reply_message_sequences_async` 中添加验证：

```python
# 在解析前检查输出完整性
if normalized_output and not self._validate_output_completeness(normalized_output):
    logger.warning(f"Rich reply checker 输出不完整，使用原始回复")
    return self.post_process_reply_message_sequences(original_reply_text)
```

## 推荐行动

1. **立即行动**：查看日志，确定问题出现在哪个环节
2. **临时方案**：禁用 `enable_rich_reply`，看问题是否消失
3. **长期方案**：
   - 如果是 token 限制，增加 `max_tokens`
   - 如果是 checker 问题，添加输出完整性验证
   - 添加不完整表情的后处理清理

## 相关文件

- `src/chat/utils/utils.py:274-454` - 分句器
- `src/chat/utils/utils.py:658-709` - 颜文字保护
- `src/chat/utils/utils.py:517-599` - LLM 响应后处理
- `src/maisaka/builtin_tool/reply.py:213-295` - Rich reply checker 调用
- `src/maisaka/builtin_tool/context.py:278-332` - Rich reply 解析
- `config/model_config.toml` - 模型配置
- `config/bot_config.toml` - 机器人配置

## 测试脚本

已创建测试脚本：
- `test_splitter_issue.py` - 测试分句器
- `test_kaomoji_pattern.py` - 测试颜文字匹配
- `test_kaomoji_simple.py` - 简单测试
- `test_full_flow.py` - 完整流程测试

运行测试：
```bash
python test_full_flow.py
```
