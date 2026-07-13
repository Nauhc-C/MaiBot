# Sakiko 统一日程与发布插件设计

## 状态

- 日期：2026-07-13
- 结论：已获用户批准
- 目标插件：`sakiko.daily-life-publisher`
- 来源实现：`xuqian13.autonomous-planning-plugin-v4` 4.4.5

## 背景

当前 `sakiko.daily-life-publisher` 已承担素材、图片、主动消息和 QQ 空间发布，但内置日程只有一个全天活动，没有时间窗。其 LLM 调用还因 Manifest 未声明 `llm.generate` 而持续失败，现存计划实际来自随机兜底。插件虽然会写入 `current_activity_context.json`，但 context-injector 不读取该文件，TOML 中的动态规则为空，因此 planner 和 replyer 无法稳定获得当前活动。

自主规划 v4 已具备多时段日程、真实人设加载、最近日程上下文、结构解析、语义校验、质量评分、当前活动查询和双阶段注入。用户明确要求将所需核心代码合并进当前插件，最终只维护一个插件，不继续依赖独立 v4 运行。

## 决策

`sakiko.daily-life-publisher` 将成为唯一日程源和唯一发布编排器。实现会移入并精简 v4 的日程核心，保留来源说明和许可证，不复制未来约定、通用目标管理、按会话日程、主动频率调节等无关能力。

合并后的插件采用 AGPL-3.0。原 v4 的版权、仓库地址和许可证信息写入 `THIRD_PARTY_NOTICES.md`，从 v4 改写的文件保留简短来源头。不得将上游代码标记为完全原创，也不得移除 AGPL 义务。

## 范围

### 包含

- 每天 7 到 10 个带开始时间和持续时长的活动。
- 每周高层计划和每日多时段计划。
- 主程序实际 bot 人设、回复风格和兴趣加载。
- 最近 3 天日程摘要和昨日连续性。
- JSON 响应解析、结构校验、关键时间校验、质量评分和最多两轮生成。
- SQLite 持久化、日期唯一约束、历史查询和生成失败记录。
- 当前活动快照、下一活动列表、planner 注入和 replyer 注入。
- 素材、图片、主动消息和 QQ 空间复用同一个活动快照。
- 发布决策与结果台账、重启防重和真实发布总闸。
- `/plan` 管理命令、公开只读 API、WebUI 现有计划页面适配。
- 独立手动测试脚本与 7 天验收、20 案例评测导出。

### 不包含

- 用户承诺自动写入日程。
- `pending_commitment`、角色裁判和通用目标 CRUD。
- 不同会话维护不同日程。
- 跨天活动；所有活动必须在本地自然日内结束。
- 按活动调节聊天频率。
- 复制 v4 的主动行为发布器。
- 删除或自动启用独立 v4 插件。

## 模块边界

### `schedule_models.py`

定义 `WeeklyPlan`、`DailySchedule`、`ScheduleActivity`、`CurrentActivitySnapshot` 和生成结果类型。活动包含稳定 ID、日期、名称、描述、类型、优先级、开始分钟、结束分钟和生成来源。

### `schedule_store.py`

只负责 SQLite 读写和事务，不包含生成或发布逻辑。数据库位于 `self.ctx.paths.data_dir / "schedule.db"`。运行时缓存和临时图片使用 `self.ctx.paths.runtime_dir`，不再向插件源码目录写新数据。

核心表：

- `weekly_plans`：`week_start` 唯一，保存主题、粗略方向、生成时间和原始 JSON。
- `daily_schedules`：`schedule_date` 唯一，保存所属周、状态、质量分、生成时间和失败摘要。
- `schedule_activities`：按日期和开始时间排序，外键关联每日计划。
- `generation_attempts`：记录模型、轮次、解析结果、验证问题和错误类别。
- `publication_attempts`：保存幂等键、窗口、渠道、概率决策、发送状态和失败原因。

### `schedule_generator.py`

协调人设、周计划、最近 3 天摘要和 LLM。它复用并改写 v4 的 prompt builder、response parser、validator 和 quality scorer，但不依赖 v4 的 GoalManager。

生成约束：

- 默认 7 到 10 个活动。
- 时间窗按开始时间严格递增，不能重叠，不能越过 24:00。
- 必须覆盖睡眠、三餐或合理替代，并至少包含两个角色化活动。
- 允许少量未安排空档，避免强制 24 小时无缝日程造成机械感。
- 结构、时间和日期属于硬校验；不通过则不落库。
- 角色贴合、描述长度和多样性属于质量评分；低于阈值时最多重试一次。
- 两轮都失败时记录失败并显式返回错误，不生成随机兜底。

### `schedule_service.py`

提供唯一业务入口：确保周计划、确保日计划、按日期读取计划、按模拟时间计算当前活动、强制重生成。日期唯一约束和事务共同避免并发或重启重复生成。

每周一首次运行时生成本周计划。每天 00:30 生成当日计划；若启动时当天没有计划，则补生成。手动指定日期生成与自动生成走同一条校验和持久化路径。

### `schedule_injector.py`

直接注册 `maisaka.planner.before_request` 和 `maisaka.replyer.before_model_request`。两个 Hook 都从 `schedule_service` 获取同一快照，不读取 context-injector TOML，也不写 `current_activity_context.json`。

planner 获得当前活动、时间窗和最多两个后续活动。replyer 获得更短的状态提示，要求自然贴合但不要每次主动复述日程。日期变化和时间窗变化通过查询当前时间自动生效。

### 发布编排

现有素材、图片和渠道投递保留，但事件构建只接受当前日程快照。图片 prompt、消息文本和主动意图不得各自选择不同活动。

新增 `publishing.allow_real_publish`，默认和迁移值均为 `false`。只要该值为 `false`：

- 自动调度可以生成日程和发布预览。
- `/daily_life publish` 返回被安全闸阻止的结果。
- Maizone API 和群主动触发 API 都不会被调用。
- WebUI 发布操作也只能执行 dry-run。

发布窗口使用稳定幂等键：`date + window + channel + content_hash`。发送前先事务写入 `in_flight`，随后才调用外部渠道。结果状态为：

- `probability_skipped`：概率未命中，未调用渠道。
- `in_flight`：已准备发送但尚无确定结果。
- `succeeded`：渠道明确成功。
- `failed`：渠道明确失败并保存原因。
- `blocked`：被真实发布总闸拦截。

重启遇到遗留 `in_flight` 时默认不自动重发，标记为需要人工核对，以优先满足“不重复发布”。

## API 与命令

保留 `/daily_life`，新增或统一以下入口：

- `/plan status [YYYY-MM-DD]`：查看指定日全部活动。
- `/plan generate [YYYY-MM-DD]`：缺失时生成。
- `/plan regenerate [YYYY-MM-DD] [额外要求]`：先生成并验证新版本，成功后事务替换旧版本；失败时保留旧计划。
- `/plan at HH:MM [YYYY-MM-DD]`：模拟时间查询当前和后续活动，不修改系统时间。
- `/daily_life dryrun [HH:MM]`：生成完整发布预览，不调用外部渠道。
- `/daily_life status`：展示日程、发布总闸和最近发布台账。
- `/plan import-legacy`：显式导入旧 JSON 计划，重复执行不会重复写入。

公开 API：

- `sakiko.daily-life-publisher.get_current_activity`
- `sakiko.daily-life-publisher.get_daily_schedule`
- `sakiko.daily-life-publisher.generate_daily_schedule`
- `sakiko.daily-life-publisher.preview_daily_life`
- `sakiko.daily-life-publisher.export_acceptance_report`

所有写 API 都遵守日期唯一约束；发布 API 额外遵守真实发布总闸。

## 手动测试入口

新增 `tests/manual_schedule_lab.py`，可以在插件未激活时运行，不依赖真实 Maizone：

```powershell
uv run python plugins/sakiko_daily_life_publisher/tests/manual_schedule_lab.py generate --date 2026-07-14
uv run python plugins/sakiko_daily_life_publisher/tests/manual_schedule_lab.py show --date 2026-07-14
uv run python plugins/sakiko_daily_life_publisher/tests/manual_schedule_lab.py at --date 2026-07-14 --time 18:30
uv run python plugins/sakiko_daily_life_publisher/tests/manual_schedule_lab.py preview --date 2026-07-14 --time 18:30
uv run python plugins/sakiko_daily_life_publisher/tests/manual_schedule_lab.py export --days 7
uv run python plugins/sakiko_daily_life_publisher/tests/manual_schedule_lab.py import-legacy
```

脚本默认使用隔离的临时 SQLite 和 fake LLM。显式提供 `--live-db` 才允许读取运行数据库，但仍不具备真实发布能力。真实 LLM 手动生成通过插件运行时的 `/plan generate` 和 `/plan regenerate` 验证；此时插件可以保持启用，只要 `publishing.allow_real_publish=false`，所有渠道调用仍会被总闸阻止。生成输出同时提供人类可读文本和 JSON，便于人工标注。

## 旧数据处理

不删除 `plugins/sakiko_daily_life_publisher/data/plans/*.json`、`publisher_state.json` 或图片。首次迁移提供显式命令，将可解析的周计划和单活动日计划标记为 `legacy` 导入标准持久化目录；不会自动导入，避免热重载时修改历史。

`current_activity_context.json` 停止更新，但保留文件作为历史证据。context-injector 中现有空规则不由本次变更修改，避免覆盖用户维护的配置。

## 错误处理

- 缺少 `llm.generate` 授权：启动检查直接报错，日程生成不可用，发布预览说明无日程；不随机兜底。
- LLM 超时或解析失败：记录 `generation_attempts`，允许有限重试，最终失败不替换已有计划。
- SQLite 写入失败：事务回滚，内存不声称成功。
- 当天无计划：注入 Hook 安静跳过，查询 API 返回结构化 `no_schedule`。
- 当前时间落在空档：返回最近已结束活动和下一活动，但 `has_activity=false`。
- 图片失败：记录图片错误；`image.allow_text_fallback=true` 时允许纯文本预览和发布，设为 `false` 时把本次渠道结果记为失败。默认值为 `true`，保持现有行为。
- 渠道失败：按渠道分别记录，不把概率未中写成发布失败。

## 测试策略

### 单元测试

- 时间解析、边界命中、空档、午夜和非法跨天。
- Schema 解析、硬校验、质量评分和第二轮重试。
- 最近 3 天摘要和重复活动检测。
- SQLite 日期唯一约束、事务替换和并发生成。
- 发布幂等键、总闸、概率未中、失败和遗留 `in_flight`。
- planner/replyer 注入使用同一活动快照。

### 集成测试

- fake LLM 生成一整天多时段计划并写入临时数据库。
- 模拟多个时间点验证当前活动切换。
- fake Maizone 验证 `allow_real_publish=false` 时零外部调用。
- 模拟成功、明确失败和发送后进程中断。
- 旧 JSON 显式导入且原文件不变。

### 手动验收

- 连续 7 天导出周计划、每日计划、当前活动、发布决策、QQ 空间结果、失败原因和次日继承。
- 从真实生成计划中累计 20 个案例，标注活动选择、时间合理性、角色贴合和昨日连续性。
- 验收前不修改角色 Prompt；先按失败类型决定修改人设上下文、素材、生成约束或校验器。

## 完成标准

- 线上只有 `sakiko.daily-life-publisher` 生成日程；独立 v4 保持禁用。
- 一天包含多个明确时段，当前活动随时间自动切换。
- planner 和 replyer 都能获得同一天同一时段的活动。
- 文本、图片和发布决策引用同一活动。
- 默认配置无法真实发布，手动测试不会调用 QQ 空间。
- 概率未中、发布失败和安全闸阻止可追溯且含不同状态。
- 重启不会自动重复发送不确定的发布尝试。
- 新周生成新计划，历史计划可按日期查询。
- 自动化测试和手动测试入口均可运行，并能导出 S2、S3 所需材料。
