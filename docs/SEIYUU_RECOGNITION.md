# SeiyuuMatch 人脸识别集成

## 功能说明

解决 MaiBot 的 VLM（视觉语言模型）经常识别错声优/角色的问题。通过在图片描述生成前先调用 SeiyuuMatch API 识别人脸，将准确的角色信息注入到 VLM 的 prompt 中，从而修正 VLM 的识别错误。

### 问题场景

**修复前**：
```
用户: [发送律酱的照片] 这是谁？
MaiBot: 这是羊宮妃那...（识别错误）
用户: ？？？
```

**修复后**：
```
用户: [发送律酱的照片] 这是谁？
MaiBot: 这是椎名立希（律酱）呢~ ✨（识别正确）
```

## 工作原理

1. **用户发送图片** → 进入 `image_manager.get_image_description()`
2. **SeiyuuMatch 识别** → `_generate_image_description()` 先调用 SeiyuuMatch API
3. **结果注入** → 将识别结果注入到 VLM 的 prompt 前面：
   ```
   【人脸识别结果】人物: 椎名立希, 来自 bangdream/avemujica（相似度 89%）。

   请用中文详细描述这张图片的内容...
   ```
4. **VLM 生成描述** → VLM 参考人脸识别结果，生成准确的描述
5. **返回给 MaiBot** → 最终描述用于对话上下文

## 配置

### 启用/禁用

编辑 `config/bot_config.toml`：

```toml
[features.seiyuu_recognition]
enabled = true  # 改为 false 可禁用
api_endpoint = "https://seiyuumatch.org"
timeout = 10.0  # API 请求超时时间（秒）
selected_groups = "bangdream:mygo,bangdream:avemujica,bangdream:sumimi"
```

### 识别范围

`selected_groups` 控制识别哪些企划/团体的声优：

- **默认**: `bangdream:mygo,bangdream:avemujica,bangdream:sumimi`
- **全部 BanG Dream**: `bangdream:mygo,bangdream:avemujica,bangdream:roselia,bangdream:afterglow,bangdream:pastel,bangdream:hhw,bangdream:ras,bangdream:morfonica`
- **LoveLive**: `lovelive:μ's,lovelive:Aqours,lovelive:虹咲,lovelive:Liella!,lovelive:莲之空`
- **跨企划**: `bangdream:mygo,lovelive:虹咲`

完整团体列表见 SeiyuuMatch README。

## 测试

### 基础识别测试

```bash
cd project/MaiBot
uv run python test_seiyuu_recognition.py <图片路径>
```

示例：
```bash
uv run python test_seiyuu_recognition.py tests/images/ritsu.jpg
```

### 完整流程测试

测试脚本会分两步：
1. 仅测试 SeiyuuMatch 识别（不调用 VLM）
2. 测试完整图片描述生成（包含 VLM）

运行后按提示操作即可。

## 文件结构

```
project/MaiBot/
├── src/chat/image_system/
│   ├── image_manager.py              # [修改] 在 _generate_image_description 中集成
│   └── seiyuu_recognizer.py          # [新增] SeiyuuMatch API 客户端
├── config/
│   └── bot_config.toml               # [修改] 添加 [features.seiyuu_recognition]
├── test_seiyuu_recognition.py        # [新增] 测试脚本
└── docs/
    └── SEIYUU_RECOGNITION.md         # 本文档
```

## API 响应格式

SeiyuuMatch API 返回示例：

```json
{
  "faces": ["椎名立希"],
  "details": [{
    "name": "椎名立希",
    "project": "bangdream",
    "group": "avemujica",
    "similarity": 0.7834,
    "display_score": 89,
    "top5": [
      {"name": "椎名立希", "display_score": 89},
      {"name": "长崎素世", "display_score": 76},
      ...
    ],
    "bbox": [0.23, 0.15, 0.78, 0.92]
  }],
  "mode": "default",
  "groups": ["bangdream:mygo", "bangdream:avemujica"],
  "queue_wait": 0.123
}
```

### 无人脸场景

如果图片中没有人脸，API 返回：
```json
{
  "faces": [],
  "details": [],
  ...
}
```

此时 SeiyuuMatch 识别会返回 `None`，不注入任何信息到 prompt，VLM 正常处理非人脸图片。

## 注意事项

1. **网络依赖**: 需要能访问 `https://seiyuumatch.org`，如果网络不通，识别会静默失败（不影响正常图片描述）
2. **超时设置**: 默认 10 秒超时，可根据网络情况调整
3. **识别失败**: API 错误、超时或无人脸时，不会中断流程，VLM 会继续生成描述
4. **仅识别人脸**: 风景、截图、表情包等非人像图片不会被识别，不影响性能
5. **识别范围**: 只识别配置的 `selected_groups` 中的声优，减少无关匹配

## 故障排查

### 识别总是返回 None

1. 检查配置是否启用: `enabled = true`
2. 检查网络连通性: `curl https://seiyuumatch.org/health`
3. 查看日志: 搜索 `SeiyuuMatch` 关键字

### 识别结果不准确

1. 调整 `selected_groups` 范围（太窄可能漏掉，太宽可能误识别）
2. 确认图片质量（模糊、侧脸、遮挡会影响准确度）
3. 查看 Top 5 候选，可能第二名才是正确结果

### VLM 仍然识别错误

1. 检查日志确认识别结果是否正确注入到 prompt
2. 可能 VLM 模型过于自信，忽略了 prompt 中的人脸识别结果
3. 尝试修改 `prompts/zh-CN/image_description.prompt`，强调"请优先参考人脸识别结果"

## 日志示例

**成功识别**:
```
[seiyuu_recognizer] SeiyuuMatch 识别成功: 1 个人脸 - 椎名立希
[image] 已将 SeiyuuMatch 识别结果注入到图片描述 prompt: 【人脸识别结果】人物: 椎名立希, 来自 bangdream/avemujica（相似度 89%）。
```

**无人脸**:
```
[seiyuu_recognizer] SeiyuuMatch 未识别到人脸
```

**网络错误**:
```
[seiyuu_recognizer] SeiyuuMatch API 请求超时 (timeout=10.0s)
```

## 开发参考

### 自定义识别范围

可以根据聊天流动态调整识别范围：

```python
from src.chat.image_system.seiyuu_recognizer import seiyuu_recognizer

# 临时修改识别范围
seiyuu_recognizer._selected_groups = "bangdream:mygo,bangdream:avemujica"

# 调用识别
result = await seiyuu_recognizer.recognize(image_bytes)
```

### 自定义 Prompt 格式

修改 `seiyuu_recognizer.py` 的 `format_recognition_for_prompt()` 方法来改变注入格式。

## 性能影响

- **额外延迟**: 每张图片增加 ~0.5-2 秒（取决于网络和 API 负载）
- **失败回退**: 如果超时或失败，不影响原有流程
- **缓存机制**: 相同图片（相同 hash）只识别一次，后续直接使用缓存

## 相关链接

- [SeiyuuMatch GitHub](https://github.com/satoshinji2992/SeiyuuMatch)
- [SeiyuuMatch 网站](https://seiyuumatch.org)
- [MaiBot AGENTS.md](../AGENTS.md)
