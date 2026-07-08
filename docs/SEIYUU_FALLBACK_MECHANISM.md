# SeiyuuMatch 三级回退机制

## 🎯 设计目标

**平衡准确度和覆盖范围**：
- 优先使用小范围（高准确度）
- 置信度不足时自动扩大范围
- 避免一开始就用大范围导致误识别

---

## 🔄 三级回退流程

### 级别 1：精准范围（3 个团）
```
配置: bangdream:mygo,bangdream:avemujica,bangdream:sumimi
候选人数: ~12 人
预期置信度: 85%+
```

**适用场景**：清晰的照片，主要关注 MyGO/Ave Mujica

### 级别 2：中等范围（5-7 个团）
```
配置: 级别1 + bangdream:roselia,bangdream:ras,bangdream:morfonica
候选人数: ~24 人
预期置信度: 75%+
```

**适用场景**：照片较模糊，或可能是其他团体成员

### 级别 3：全覆盖（13 个团）
```
配置: 全部 BanG Dream 团体
候选人数: ~60 人
预期置信度: 60%+
```

**适用场景**：极模糊照片，或不常见的团体成员

---

## 📊 工作流程示例

### 示例 1：高置信度（一次成功）

```
用户发送: [律酱清晰照片]

级别 1 (3团):
→ API 请求: groups=bangdream:mygo,bangdream:avemujica,bangdream:sumimi
→ 识别结果: 椎名立希 (89%)
→ 89% >= 60% (阈值) ✅
→ 直接返回结果

日志:
[seiyuu_recognizer] SeiyuuMatch 识别成功 (级别 1): 1 个人脸 - 椎名立希 (平均置信度 89%)

总耗时: ~210ms
API 调用次数: 1
```

---

### 示例 2：中等置信度（二次回退）

```
用户发送: [模糊的照片]

级别 1 (3团):
→ API 请求: groups=bangdream:mygo,bangdream:avemujica,bangdream:sumimi
→ 识别结果: 长崎素世 (55%)
→ 55% < 60% (阈值) ❌
→ 触发回退

日志:
[seiyuu_recognizer] SeiyuuMatch 识别置信度不足 (级别 1: 55% < 60%)，尝试扩大识别范围到级别 2

级别 2 (5-7团):
→ API 请求: groups=bangdream:mygo,bangdream:avemujica,bangdream:sumimi,bangdream:roselia,bangdream:ras,bangdream:morfonica
→ 识别结果: 今井リサ (72%)  ← 原来是 Roselia 成员！
→ 72% >= 60% (阈值) ✅
→ 返回结果

日志:
[seiyuu_recognizer] SeiyuuMatch 识别成功 (级别 2): 1 个人脸 - 今井リサ (平均置信度 72%)

总耗时: ~210ms + ~275ms = ~485ms
API 调用次数: 2
```

---

### 示例 3：低置信度（三次回退）

```
用户发送: [极模糊的侧脸照片]

级别 1 (3团):
→ 识别结果: 高松灯 (48%)
→ 48% < 60% ❌ → 回退

级别 2 (5-7团):
→ 识别结果: 湊友希那 (52%)
→ 52% < 60% ❌ → 回退

级别 3 (全BanG Dream):
→ 识别结果: 戸山香澄 (65%)  ← 原来是 Poppin'Party！
→ 65% >= 60% ✅
→ 返回结果

日志:
[seiyuu_recognizer] SeiyuuMatch 识别置信度不足 (级别 1: 48% < 60%)，尝试扩大识别范围到级别 2
[seiyuu_recognizer] SeiyuuMatch 识别置信度不足 (级别 2: 52% < 60%)，尝试扩大识别范围到级别 3
[seiyuu_recognizer] SeiyuuMatch 识别完成 (级别 3，最终): 1 个人脸 - 戸山香澄 (平均置信度 65%)

总耗时: ~210ms + ~275ms + ~450ms = ~935ms
API 调用次数: 3
```

---

### 示例 4：仍然不足（返回最终结果）

```
用户发送: [极度模糊/遮挡的照片]

级别 1: 椎名立希 (45%) ❌
级别 2: 長崎素世 (50%) ❌
级别 3: 高松灯 (58%) ❌ 仍然 < 60%

→ 已达到最高级别，返回当前最佳结果

日志:
[seiyuu_recognizer] SeiyuuMatch 识别完成 (级别 3，最终): 1 个人脸 - 高松灯 (平均置信度 58%)
[image] 识别置信度较低 (58%)，将在图片描述中添加不确定性提示

→ 图片描述: "...（人脸识别置信度 58%，可能是 高松灯）"
→ Planner 看到不确定性，谨慎回复

总耗时: ~935ms
API 调用次数: 3
```

---

## ⚙️ 配置选项

### 在 `config/bot_config.toml` 中配置：

```toml
[features.seiyuu_recognition]
enabled = true
api_endpoint = "http://127.0.0.1:3724"
timeout = 10.0
selected_groups = "bangdream:mygo,bangdream:avemujica,bangdream:sumimi"

# 三级回退配置
enable_fallback = true      # 是否启用回退机制
fallback_threshold = 60.0   # 触发回退的置信度阈值（%）
```

---

## 📐 阈值设置建议

| 阈值 | 效果 | 适用场景 |
|------|------|---------|
| **50** | 很容易触发回退 | 要求极高准确度，宁可扩大范围 |
| **60** | 适中触发（推荐） | 平衡准确度和性能 |
| **70** | 较难触发 | 更信任小范围结果，减少 API 调用 |
| **80** | 很少触发 | 几乎不回退，优先性能 |

---

## 🎯 优势分析

### 与固定范围对比

#### 方案 A：固定小范围（3 个团）
```
优点: 速度快(210ms)，准确度高(85%+)
缺点: 无法识别其他团体成员 ❌
```

#### 方案 B：固定大范围（全BanG Dream）
```
优点: 覆盖范围广
缺点: 速度慢(450ms)，准确度低(70%-)，误识别多 ❌
```

#### 方案 C：三级回退（推荐）✅
```
优点: 
- 大部分情况快速准确(210ms, 85%+)
- 必要时自动扩大范围
- 覆盖所有场景
缺点:
- 低置信度场景较慢(最多 935ms)
- 实现稍复杂
```

---

## 📊 性能统计（预估）

### 假设照片分布
- 70% 是 MyGO/Ave Mujica（级别 1 成功）
- 20% 是其他团体（级别 2-3 成功）
- 10% 极模糊（级别 3 失败）

### 平均性能
```
平均耗时 = 70% × 210ms + 20% × 485ms + 10% × 935ms
         = 147ms + 97ms + 93.5ms
         = 337.5ms

平均 API 调用 = 70% × 1 + 20% × 2 + 10% × 3
             = 0.7 + 0.4 + 0.3
             = 1.4 次/图片
```

**对比固定方案**：
- 固定 3 团：210ms，但 30% 识别失败
- 固定全团：450ms，70% 的情况浪费性能
- 三级回退：337ms，覆盖所有情况 ✅

---

## 🔧 高级用法

### 禁用回退（固定范围）
```toml
enable_fallback = false
selected_groups = "bangdream:mygo,bangdream:avemujica,bangdream:sumimi"
```
→ 只使用配置的范围，不回退

### 自定义阈值
```toml
fallback_threshold = 70.0  # 提高阈值，更容易触发回退
```

### 自定义初始范围
```toml
selected_groups = "bangdream:roselia,bangdream:ras"  # 从 Roselia 开始
```
→ 级别 1: Roselia, RAS
→ 级别 2: + Morfonica
→ 级别 3: 全 BanG Dream

---

## 📝 日志解读

### 正常识别（级别 1）
```
[seiyuu_recognizer] SeiyuuMatch 识别已启用，API: http://127.0.0.1:3724, groups: bangdream:mygo,..., 回退机制: 启用
[seiyuu_recognizer] SeiyuuMatch 识别成功 (级别 1): 1 个人脸 - 椎名立希 (平均置信度 89%)
```

### 触发回退（级别 2）
```
[seiyuu_recognizer] SeiyuuMatch 识别置信度不足 (级别 1: 55% < 60%)，尝试扩大识别范围到级别 2
[seiyuu_recognizer] SeiyuuMatch 识别成功 (级别 2): 1 个人脸 - 今井リサ (平均置信度 72%)
```

### 最终级别（级别 3）
```
[seiyuu_recognizer] SeiyuuMatch 识别置信度不足 (级别 1: 48% < 60%)，尝试扩大识别范围到级别 2
[seiyuu_recognizer] SeiyuuMatch 识别置信度不足 (级别 2: 52% < 60%)，尝试扩大识别范围到级别 3
[seiyuu_recognizer] SeiyuuMatch 识别完成 (级别 3，最终): 1 个人脸 - 戸山香澄 (平均置信度 65%)
```

---

## ✅ 总结

**三级回退机制的核心价值**：

1. **智能权衡**：在准确度和覆盖范围之间自动平衡
2. **性能优化**：大部分情况快速返回，只在必要时扩大范围
3. **用户友好**：无需手动切换配置，自动适应不同照片质量
4. **可配置**：支持调整阈值和禁用回退

**适用场景**：
- ✅ 主要关注特定团体，偶尔有其他团体
- ✅ 照片质量参差不齐
- ✅ 需要平衡准确度和性能

**不适用场景**：
- ❌ 完全随机的各团体照片 → 建议直接用全范围
- ❌ 全部是清晰照片 → 建议禁用回退，固定小范围
