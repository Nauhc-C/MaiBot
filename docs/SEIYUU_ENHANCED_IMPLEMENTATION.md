# SeiyuuMatch 增强版实现说明

## 实现的改进

### 1. **增强的识别结果格式**

#### 单人脸场景
```
【人脸识别结果】人物: 椎名立希, 来自 bangdream/avemujica（识别置信度 89%）。
```

#### 多人脸场景（带位置标注）
```
【人脸识别结果】图左侧的人物: 高松灯, 来自 bangdream/mygo（识别置信度 92%）；图右侧的人物: 椎名立希, 来自 bangdream/avemujica（识别置信度 87%）。
```

#### 低置信度场景（<70%）
```
【人脸识别结果】人物: 长崎素世, 来自 bangdream/avemujica（识别置信度 65%）。
注意：识别置信度较低，请结合图片内容综合判断。
```

---

## 数据流详解

### 第一层：SeiyuuMatch → Gemini VLM

```python
# 1. SeiyuuMatch 识别人脸
seiyuu_result = {
    "faces": ["椎名立希"],
    "details": [{
        "name": "椎名立希",
        "project": "bangdream",
        "group": "avemujica",
        "similarity": 0.89,
        "display_score": 89,
        "bbox": [0.23, 0.15, 0.78, 0.92]  # [x1, y1, x2, y2] 归一化坐标
    }]
}

# 2. 格式化为注入文本
seiyuu_info = "【人脸识别结果】人物: 椎名立希, 来自 bangdream/avemujica（识别置信度 89%）。"

# 3. 注入到 Gemini 的 prompt
prompt = f"{seiyuu_info}\n\n请用中文详细描述这张图片的内容..."

# 4. Gemini 生成描述（参考了 SeiyuuMatch 的结果）
vlm_description = "这张图片展示了椎名立希（律酱），她身穿黑色哥特风服装..."
```

**关键点**：
- ✅ Gemini 看到了 SeiyuuMatch 的识别结果
- ✅ Gemini 基于这个"ground truth"生成描述，不会再说"无法识别是谁"
- ✅ 即使 Gemini 原本会识别错，看到明确的识别结果后会修正

---

### 第二层：VLM 描述 → Planner/Replyer

```python
# 5. VLM 描述存入 ImageComponent.content
component.content = "[图片：这张图片展示了椎名立希（律酱）...]"

# 6. 如果置信度 < 70%，添加不确定性提示
if avg_score < 70:
    component.content += "（人脸识别置信度 65%，可能是 长崎素世）"
    # 最终: "[图片：这张图片展示了一位女性...（人脸识别置信度 65%，可能是 长崎素世）]"

# 7. 传递给 Planner
planner_input = {
    "user_message": "[图片：...] 这是谁？",
    # Planner 看到了完整的描述 + 可能的不确定性提示
}

# 8. Planner 决策
if "人脸识别置信度" in description and score < 70:
    # Planner 知道识别不确定，可以更谨慎地回复
    reply_guide = "识别结果不确定，以询问或委婉的方式回复"
else:
    reply_guide = "自信地回答是谁"
```

---

## 完整示例

### 示例 1：高置信度识别（89%）

**用户发送**：[律酱照片] "这是谁？"

**处理流程**：
```
1. SeiyuuMatch 识别:
   识别到: 椎名立希 (89%)
   位置: 图中 (单人脸)

2. 注入到 Gemini prompt:
   【人脸识别结果】人物: 椎名立希, 来自 bangdream/avemujica（识别置信度 89%）。
   
   请用中文详细描述这张图片的内容...

3. Gemini 生成描述:
   "这张图片展示了椎名立希（律酱），她身穿黑色哥特风服装，表情温柔..."

4. 传递给 Planner:
   [图片：这张图片展示了椎名立希（律酱），她身穿黑色哥特风服装...] 这是谁？

5. Planner 决策:
   识别结果明确，自信回复

6. Replyer 生成:
   "这是律酱呢~ 今天的造型真好看✨"
```

**日志输出**：
```
[seiyuu_recognizer] SeiyuuMatch 识别成功: 1 个人脸 - 椎名立希
[image] 已将 SeiyuuMatch 识别结果注入到图片描述 prompt
[image] SeiyuuMatch 注入内容:
【人脸识别结果】人物: 椎名立希, 来自 bangdream/avemujica（识别置信度 89%）。
[image] 完整 VLM prompt (前200字):
【人脸识别结果】人物: 椎名立希, 来自 bangdream/avemujica（识别置信度 89%）。

请用中文详细描述这张图片的内容。如果有文字，请把文字描述概括出来，请留意其主题、直观感受，输出为一段平文本，最多100字，请注意不要分点，就输出一段文本...
[image] VLM 生成的描述 (前150字):
这张图片展示了椎名立希（律酱），她身穿黑色哥特风服装，表情温柔...
```

---

### 示例 2：低置信度识别（65%）

**用户发送**：[模糊的照片] "这是谁？"

**处理流程**：
```
1. SeiyuuMatch 识别:
   识别到: 长崎素世 (65%)
   置信度较低！

2. 注入到 Gemini prompt:
   【人脸识别结果】人物: 长崎素世, 来自 bangdream/avemujica（识别置信度 65%）。
   注意：识别置信度较低，请结合图片内容综合判断。
   
   请用中文详细描述这张图片的内容...

3. Gemini 生成描述:
   "这张图片展示了一位留着浅色短发的年轻女性，身穿白色服装..."
   （Gemini 可能因为模糊没有明确说是素世）

4. 添加不确定性提示:
   描述 += "（人脸识别置信度 65%，可能是 长崎素世）"

5. 传递给 Planner:
   [图片：这张图片展示了一位留着浅色短发的年轻女性...（人脸识别置信度 65%，可能是 长崎素世）] 这是谁？

6. Planner 决策:
   看到"识别置信度 65%"，知道不确定，采用谨慎回复策略

7. Replyer 生成:
   "嗯...看起来可能是素世？不过照片有点模糊，不太确定呢~"
```

**日志输出**：
```
[seiyuu_recognizer] SeiyuuMatch 识别成功: 1 个人脸 - 长崎素世
[image] 已将 SeiyuuMatch 识别结果注入到图片描述 prompt
[image] 识别置信度较低 (65%)，将在图片描述中添加不确定性提示
[image] VLM 生成的描述 (前150字):
这张图片展示了一位留着浅色短发的年轻女性...
[image] 已在图片描述中添加不确定性提示: （人脸识别置信度 65%，可能是 长崎素世）
```

---

### 示例 3：多人脸场景

**用户发送**：[合照] "她们是谁？"

**处理流程**：
```
1. SeiyuuMatch 识别:
   识别到 2 个人脸:
   - 人脸1: bbox=[0.15, 0.2, 0.45, 0.8] → 中心x=0.3 → 图左侧
     高松灯 (92%)
   - 人脸2: bbox=[0.55, 0.2, 0.85, 0.8] → 中心x=0.7 → 图右侧
     椎名立希 (87%)

2. 注入到 Gemini prompt:
   【人脸识别结果】图左侧的人物: 高松灯, 来自 bangdream/mygo（识别置信度 92%）；图右侧的人物: 椎名立希, 来自 bangdream/avemujica（识别置信度 87%）。
   
   请用中文详细描述这张图片的内容...

3. Gemini 生成描述:
   "这张合照中，图左侧是高松灯，穿着红色卫衣；图右侧是椎名立希，穿着黑色服装..."

4. 传递给 Planner:
   [图片：这张合照中，图左侧是高松灯...图右侧是椎名立希...] 她们是谁？

5. Replyer 生成:
   "左边是灯酱，右边是律酱呢~ 两位一起的合照真难得✨"
```

**日志输出**：
```
[seiyuu_recognizer] SeiyuuMatch 识别成功: 2 个人脸 - 高松灯, 椎名立希
[image] 已将 SeiyuuMatch 识别结果注入到图片描述 prompt
[image] SeiyuuMatch 注入内容:
【人脸识别结果】图左侧的人物: 高松灯, 来自 bangdream/mygo（识别置信度 92%）；图右侧的人物: 椎名立希, 来自 bangdream/avemujica（识别置信度 87%）。
```

---

## 为什么在 MaiBot 的提示词日志里看不到？

### 原因分析

MaiBot 的 LLM 请求日志通常记录的是：
- **Planner 的请求**（包含聊天历史、工具等）
- **Replyer 的请求**（包含回复指导等）

但是：
- **VLM（Gemini）的请求**是在 `utils_model.py` 中单独处理的
- VLM 请求日志可能在 `llm_request/` 目录下，或者被 debug 级别过滤了

### 查看完整 prompt 的方法

1. **启用 debug 日志**（在 `config/bot_config.toml` 中）：
   ```toml
   [log]
   level = "DEBUG"  # 从 INFO 改为 DEBUG
   ```

2. **查看特定日志**：
   ```bash
   # 查看图片相关的 debug 日志
   grep -i "seiyuu\|vlm prompt" logs/app_*.log.jsonl | jq -r '.event'
   ```

3. **查看 LLM 请求日志**：
   ```bash
   # VLM 请求可能在这里
   ls -lht logs/llm_request/
   ```

---

## 置信度阈值说明

### 当前设置
- **<70%**: 低置信度，添加不确定性提示到 Planner
- **70-85%**: 中等置信度，正常处理
- **>85%**: 高置信度，完全信任

### 可调整配置
如果需要调整阈值，可以在配置中添加：

```toml
[features.seiyuu_recognition]
enabled = true
api_endpoint = "http://127.0.0.1:3724"
timeout = 10.0
selected_groups = "bangdream:mygo,bangdream:avemujica,bangdream:sumimi"
low_confidence_threshold = 70  # 低于此值视为低置信度
```

---

## 优势总结

### ✅ 解决了你提到的问题

1. **位置信息**：多人脸场景自动标注"图左侧"/"图右侧"/"图中央"
2. **置信度信息**：每个识别结果都带置信度百分比
3. **避免 Gemini 返回"无法识别"**：通过注入明确的识别结果作为先验信息
4. **不会打架**：
   - 高置信度：Gemini 直接采纳，不会冲突
   - 低置信度：Gemini 谨慎判断 + Planner 知道不确定性
5. **完整日志**：debug 级别可以看到完整的注入 prompt 和 VLM 响应
6. **传递给 Planner**：低置信度场景会在描述末尾添加不确定性提示

---

## 测试建议

### 测试 1：高置信度场景
```
发送: 清晰的律酱正脸照
预期: 
- 日志显示 89%+ 置信度
- VLM 描述包含"椎名立希"
- MaiBot 自信回复"这是律酱"
```

### 测试 2：低置信度场景
```
发送: 模糊/侧脸/遮挡的照片
预期:
- 日志显示 <70% 置信度
- 描述末尾带"（人脸识别置信度 XX%，可能是 XXX）"
- MaiBot 谨慎回复"可能是..."
```

### 测试 3：多人脸场景
```
发送: 灯和律的合照
预期:
- 日志显示 2 个人脸
- 注入文本包含"图左侧...图右侧..."
- VLM 描述包含位置信息
- MaiBot 分别识别两人
```

### 测试 4：无人脸场景
```
发送: 风景/物体照片
预期:
- SeiyuuMatch 返回无人脸
- VLM 正常描述场景
- MaiBot 正常回复
```
