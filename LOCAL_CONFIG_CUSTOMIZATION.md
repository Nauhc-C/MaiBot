# 本地配置自定义说明

本文件说明如何在不被上游merge覆盖的前提下自定义MaiBot配置。

## 原则

1. **配置优先** - 通过配置项控制行为，而不是硬编码
2. **版本独立** - 使用本地版本号（如8.14.27），区别于上游版本号
3. **代码防御** - 在代码中检查配置项是否存在，提供默认值
4. **文档记录** - 在此文件记录所有本地自定义配置

## 已添加的本地自定义配置

### 1. `response_splitter.disable_too_long_fallback`

**版本**: 8.14.27（本地）  
**位置**: `config/bot_config.toml` → `response_splitter` → `disable_too_long_fallback`  
**默认值**: `false`（保持上游行为兼容）

**功能**: 
- 当设为 `true` 时，回复过长不会返回"sakiko不知道哦"等默认回复
- 而是继续处理原始回复（可能会被分割或截断）

**代码位置**:
- 配置定义: `src/config/official_configs.py:4384` (ResponseSplitterConfig类)
- 使用位置: `src/chat/utils/utils.py:544` (process_llm_response函数)

**如何启用**:
1. **通过WebUI**: 
   - 打开 http://127.0.0.1:18001/config/bot
   - 找到"响应处理" → "回复分割器" → "禁用过长回复兜底"
   - 开启开关

2. **通过配置文件**:
   ```toml
   [response_splitter]
   disable_too_long_fallback = true
   ```

**Merge安全性**: 
- ✅ 配置项名称独特，不太可能与上游冲突
- ✅ 使用本地版本号8.14.27，与上游版本号分开
- ✅ 代码中有条件判断，即使配置不存在也会使用默认行为
- ⚠️ 如果上游修改了`process_llm_response`函数的这部分逻辑，merge时需要手动检查

**Merge冲突时的处理**:
如果merge时 `src/chat/utils/utils.py:544` 附近有冲突:
1. 保留上游的主逻辑
2. 在返回默认回复的地方添加 `disable_too_long_fallback` 检查:
   ```python
   if get_western_ratio(cleaned_text) < 0.1 and len(cleaned_text) > max_length:
       if global_config.response_splitter.disable_too_long_fallback:
           logger.warning(f"回复过长 ({len(cleaned_text)} 字符)，已禁用默认兜底，继续处理原始回复")
           # 不返回默认回复，继续处理
       else:
           logger.warning(f"回复过长 ({len(cleaned_text)} 字符)，返回默认回复")
           return [_get_random_default_reply()]
   ```

---

## 添加新的本地自定义配置的模板

### 步骤1: 定义配置项

在 `src/config/official_configs.py` 的相应配置类中添加字段:

```python
class SomeConfig(ConfigBase):
    your_custom_option: bool = Field(
        default=False,  # 默认值保持兼容上游
        json_schema_extra={
            "label": {
                "zh_CN": "你的配置项名称",
                "en_US": "Your config name",
                "ja_JP": "設定名",
            },
            "x-widget": "switch",  # 或 "input", "slider" 等
            "x-icon": "icon-name",
            "description": {
                "zh_CN": "详细说明",
                "en_US": "Description",
                "ja_JP": "説明",
            },
        },
    )
    """配置项的文档字符串"""
```

### 步骤2: 使用配置项

在代码中使用，添加防御性检查:

```python
from src.config import config as config_module

# 防御性访问（如果配置不存在，使用默认值）
enable_feature = getattr(
    config_module.global_config.some_section, 
    'your_custom_option', 
    False  # 默认值
)

if enable_feature:
    # 你的自定义逻辑
    pass
else:
    # 上游默认行为
    pass
```

### 步骤3: 更新版本号

在 `src/config/config.py` 中递增版本号:

```python
CONFIG_VERSION: str = "8.14.28"  # 递增修订号
```

### 步骤4: 记录到本文档

在上面的"已添加的本地自定义配置"部分添加条目。

### 步骤5: 提交

```bash
git add -A
git commit -m "feat(config): 添加 your_custom_option 配置项

[详细说明]

配置版本号: 8.14.27 -> 8.14.28

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Merge时的检查清单

每次merge上游更新后，检查以下内容:

- [ ] 配置版本号是否正确（使用本地版本号）
- [ ] 本地自定义配置项是否还在 `official_configs.py` 中
- [ ] 使用自定义配置的代码是否受到影响
- [ ] WebUI是否能正常显示和修改自定义配置
- [ ] 运行测试确保功能正常

---

**维护者**: Nauhc-C  
**最后更新**: 2026-07-05
