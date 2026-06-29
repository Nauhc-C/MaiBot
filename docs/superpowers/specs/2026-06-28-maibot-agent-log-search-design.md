# MaiBot Agent Log Search CLI 设计稿

## 背景

MaiBot 现在已经有两类很有价值、但不适合直接整段喂给 agent 的日志：

- `logs/maisaka_prompt/` 下的推理过程日志，网页端已经能按阶段、会话、文件做分页浏览。
- `logs/*.log.jsonl`、`logs/**` 下的运行期日志，包含消息流转、planner、replyer、工具调用、异常等上下文。

用户希望有一个专门给 agent 用的 CLI：先按时间、具体回复、关键句、范围等条件找“候选上下文索引”，再由 agent 自己决定要读哪一段原文，而不是一次性返回全量日志。

## 目标

- 提供一个只读的日志检索 CLI。
- 默认只返回索引和摘要，不返回完整正文。
- 支持按时间范围、会话、阶段、关键词、精确句子、上下文窗口检索。
- 能把同一轮里的 planner / replyer / user 片段关联起来，方便 agent 顺藤摸瓜。
- 输出对机器友好，默认 JSON，便于后续被其它 agent 或脚本直接消费。

## 非目标

- 不做日志写入、修复、重放。
- 不做网页端 UI 改造。
- 不把所有日志预先塞进大模型上下文。
- 不改变现有聊天主流程和配置结构。

## 总体方案

新增一个独立 CLI 入口，建议命名为 `maibot-log`，实现上保留 `python -m src.cli.log_search` 的可运行入口。

CLI 由两层组成：

- 索引层：扫描日志目录，把每条可检索记录整理成统一的轻量索引。
- 检索层：根据用户条件返回命中列表，必要时再按 `entry_id` 或 `context_id` 读取原文片段。

检索默认只返回：

- 命中记录的基本元数据
- 1 到 3 行摘要
- 片段位置指针
- 建议下一步读取的上下文范围

真正的正文只在 `inspect` / `context` 这类显式命令里读取。

## 数据源范围

v1 先覆盖项目根目录下的日志树，重点包括：

- `logs/maisaka_prompt/**`
- `logs/*.log.jsonl`
- `logs/**/*.jsonl`
- `logs/**/*.txt`
- `logs/**/*.html`

解析时按“来源适配器”分类，而不是按文件名硬编码业务逻辑：

- 推理过程日志适配器：识别 planner / replyer / prompt / reasoning / action 等段落。
- JSONL 运行日志适配器：按行切分为事件记录。
- 文本日志适配器：按时间戳和日志级别切分为记录。

## 索引模型

建议使用本地 SQLite 索引库，放在仓库工作目录下的专用位置，例如 `work/log_search_index.sqlite3`。

核心表建议如下：

- `log_sources`
  - `source_id`
  - `source_path`
  - `source_kind`
  - `mtime`
  - `size`
  - `content_hash`
- `log_entries`
  - `entry_id`
  - `source_id`
  - `timestamp`
  - `chat_id`
  - `session_id`
  - `stage`
  - `actor`
  - `record_type`
  - `title`
  - `preview`
  - `body_ref`
  - `line_start`
  - `line_end`
  - `char_start`
  - `char_end`
  - `sequence_no`
- `log_entry_fts`
  - 对 `title`、`preview`、`normalized_text` 建全文索引

索引不保存大段正文，只保存：

- 可检索文本
- 位置指针
- 预览
- 归属信息

这样可以把“找线索”和“读原文”拆开，降低 token 消耗。

## 命令设计

### `search`

按条件找候选记录，只返回索引结果。

示例：

```bash
maibot-log search --contains "这句话" --time-from "2026-06-23 00:00:00" --time-to "2026-06-24 00:00:00" --limit 20
maibot-log search --stage planner --chat-id xxx --exact "某句原文"
maibot-log search --actor replyer --around 3 --contains "关键词"
```

输出默认 JSON，字段建议：

- `query`
- `total`
- `returned`
- `truncated`
- `items[]`

每个 `item` 至少包含：

- `entry_id`
- `source_path`
- `timestamp`
- `chat_id`
- `session_id`
- `stage`
- `actor`
- `record_type`
- `score`
- `preview`
- `match_spans`
- `read_hints`

### `inspect`

按 `entry_id` 读取某条记录的摘要与元数据。

它仍然不默认返回大正文，只给：

- 记录元数据
- 命中片段
- 关联上下文指针

### `context`

按 `entry_id` 读取前后窗口。

示例：

```bash
maibot-log context --entry-id abc --before 8 --after 12
```

适合 agent 在拿到候选项后，决定是否展开更大上下文。

### `reindex`

重建或增量更新索引。

默认增量扫描，必要时可强制全量重建。

## 检索语义

### 时间

- 默认按日志记录的真实时间戳筛选。
- 时间输入支持常见 CLI 日期时间格式，优先与现有脚本的解析习惯保持一致。
- 范围边界包含起止时刻。

### 关键词与精确句子

- `--contains` 做包含匹配。
- `--exact` 做精确短句匹配。
- 文本会先做基础归一化：空白折叠、全角半角和换行处理一致化。

### 范围与上下文

- `--around N` 代表围绕命中记录取前后 N 条。
- `--before` / `--after` 适合读一轮 planner/replyer 链路。
- 同一 `chat_id + stage + sequence_no` 的连续记录优先视为一个自然上下文块。

### 角色与阶段

支持至少这些过滤维度：

- `stage=planner|replyer|all`
- `actor=user|assistant|planner|replyer|tool|system`
- `chat_id`
- `session_id`

## 返回策略

搜索阶段只给“索引卡片”，不返回全量正文。

每条卡片建议包含：

- 一句话摘要
- 命中的字段
- 来源文件
- 发生时间
- 所属会话
- 建议读取窗口

如果命中很多，只返回前 `limit` 条，并明确标记 `truncated=true`。

## 错误处理

- 时间格式非法时直接报错，不自动猜测。
- 找不到索引库时提示先 `reindex`。
- 原始日志缺失时，索引项保留但标记为不可展开。
- 解析失败的文件要记录错误，不要静默吞掉。

## 与现有网页端的关系

网页端已有推理过程浏览页，能按阶段和会话浏览 `logs/maisaka_prompt/` 下的内容。
这个 CLI 不是替代网页端，而是把同一类“先看索引，再决定读什么”的模式搬给 agent。

后续如果需要，可以把 CLI 的索引层抽成公共服务，供网页端和命令行共用。

## 实现切分

建议拆成三块：

- `src/cli/log_search.py`
  - 命令行入口
  - 参数解析
  - JSON / text 输出
- `src/services/log_search/`
  - 索引构建
  - 搜索
  - 上下文展开
- `src/services/log_search/adapters/`
  - `prompt_log_adapter`
  - `jsonl_log_adapter`
  - `text_log_adapter`

这样后续加新日志源时，只补适配器，不改 CLI 核心。

## 验收标准

- `search` 默认不输出正文。
- 能按时间范围、关键词、精确句子、会话、阶段检索。
- 能返回 planner / replyer / user 的关联索引。
- `inspect` / `context` 能按索引条目展开原文。
- 结果稳定可机器解析。

## 测试建议

- 适配器单测：给定小型日志样本，能稳定切出记录和时间戳。
- 搜索单测：时间范围、contains、exact、around 的组合行为正确。
- 索引增量测试：文件未变时不重复写入，文件变更后能更新。
- CLI 输出测试：JSON schema 稳定，字段不缺失。

## 约束与后续

这版先只做“找得到、读得少、指向清楚”。

如果后续确实需要更强的语义检索，可以再加：

- 同义词扩展
- 语义向量索引
- 与网页端共用的检索 API

