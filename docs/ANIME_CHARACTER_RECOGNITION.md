# 动漫角色识别方案

## 当前状况

- **SeiyuuMatch**：仅识别真人声优（InsightFace + 真人数据库）
- **Gemini VLM**：可以识别动漫角色，但经常不准确

---

## 推荐方案：增强 Gemini VLM 的角色识别

### 方法 1：为 Gemini 提供角色参考库

在 `image_description.prompt` 中添加角色提示：

```
如果图片中包含以下动漫角色，请明确指出角色名字：

【BanG Dream! 角色】
MyGO!!!!!：
- 高松灯（たかまつ あかり）- 粉红色短发，吉他手
- 长崎素世（ながさき そよ）- 浅色短发，贝斯手  
- 椎名立希（しいな たき）- 黑色长发，键盘手
- 丰川祥子（とよかわ さちこ）- 棕色长发，鼓手
- 千早爱音（ちはや あのん）- 绿色长发，主唱

Ave Mujica：
- 椎名立希 / Oblivionis（黑色哥特装扮）
- 长崎素世 / Doloris（白色哥特装扮）
- 高松灯 / Mortis（粉色哥特装扮）
- 丰川祥子 / Timoris（棕色哥特装扮）
- 海老原美々子 / Amoris（黑红色哥特装扮）

【识别要点】
- 如果不确定具体是谁，请说"可能是XXX"
- 如果是常见的装扮或场景，请描述特征
- 如果完全无法识别，说"无法确定是哪个角色"

请用中文详细描述这张图片的内容...
```

**优点**：
- ✅ 利用现有 Gemini VLM，无需额外服务
- ✅ 可以识别动漫角色 + 声优照片
- ✅ Gemini 的多模态能力强，可以理解角色特征

**缺点**：
- ❌ prompt 变长，增加 token 消耗
- ❌ 依赖 Gemini 的识别能力，可能不如专门模型准确

---

### 方法 2：集成专门的动漫角色识别 API

类似 SeiyuuMatch 的架构，增加一个 `AnimeCharacterRecognizer`：

```python
# anime_character_recognizer.py

class AnimeCharacterRecognizer:
    """动漫角色识别器"""
    
    async def recognize(self, image_bytes: bytes) -> dict | None:
        """识别动漫角色。
        
        Returns:
            {
                "characters": ["高松灯", "椎名立希"],
                "details": [
                    {
                        "name": "高松灯",
                        "series": "BanG Dream!",
                        "group": "MyGO!!!!!",
                        "confidence": 0.92,
                        "bbox": [0.1, 0.2, 0.4, 0.8]
                    }
                ]
            }
        """
        # 调用动漫角色识别 API
        # 例如：Anime-Face-Detector, DeepDanbooru 等
```

**集成流程**：
```python
# image_manager.py: _generate_image_description()

# 1. 先判断是真人还是动漫
image_type = detect_image_type(image_bytes)  # "real" or "anime"

# 2. 根据类型选择识别器
if image_type == "real":
    recognition = await seiyuu_recognizer.recognize(image_bytes)
elif image_type == "anime":
    recognition = await anime_character_recognizer.recognize(image_bytes)

# 3. 注入到 VLM prompt
if recognition:
    info = format_recognition_for_prompt(recognition)
    prompt = f"{info}\n\n{prompt}"
```

**优点**：
- ✅ 专门模型，识别准确度高
- ✅ 可以同时支持真人声优 + 动漫角色
- ✅ 架构统一，易于扩展

**缺点**：
- ❌ 需要额外部署动漫角色识别服务
- ❌ 需要构建动漫角色数据库
- ❌ 增加系统复杂度

---

### 方法 3：使用 DeepDanbooru / WD14 Tagger

这些是专门用于识别动漫图片标签的模型：

**DeepDanbooru**：
- 可以识别角色、风格、特征等标签
- 例如：`1girl, long_hair, black_dress, gothic_style`

**WD14 Tagger**：
- 更新的模型，准确度更高
- 可以识别角色名、服装、场景等

**集成示例**：
```python
import requests

def recognize_anime_tags(image_bytes: bytes) -> list[str]:
    """使用 WD14 Tagger 识别动漫图片标签。"""
    # 调用本地部署的 WD14 Tagger 服务
    response = requests.post(
        "http://localhost:7860/api/predict",
        files={"image": image_bytes}
    )
    tags = response.json()["tags"]
    # 返回: ["takamatsulamp", "mygo!!!!!", "pink_hair", "guitar", ...]
    return tags
```

**优点**：
- ✅ 开源免费
- ✅ 可以本地部署
- ✅ 识别准确度较高

**缺点**：
- ❌ 返回的是标签（tag），不是完整的角色名
- ❌ 需要映射标签到角色名（例如 `takamatsulamp` → `高松灯`）

---

## 推荐实现方案

### 短期方案（立即可用）：增强 Gemini prompt

**步骤**：
1. 修改 `prompts/zh-CN/image_description.prompt`
2. 添加常见角色的特征描述
3. 测试效果

**成本**：低（只需修改 prompt）
**效果**：中等（依赖 Gemini 能力）

---

### 长期方案（最佳效果）：集成 WD14 Tagger

**步骤**：
1. 部署 WD14 Tagger 服务
2. 创建 `anime_character_recognizer.py`
3. 构建标签到角色名的映射表
4. 集成到 `image_manager.py`

**成本**：中等（需要部署额外服务）
**效果**：高（专门模型，准确度高）

---

## 你想采用哪种方案？

1. **简单快速**：增强 Gemini prompt（修改 `image_description.prompt`）
2. **最佳效果**：集成 WD14 Tagger（需要额外部署）
3. **暂不处理**：SeiyuuMatch 继续只识别真人声优

我可以帮你实现任何一种方案！
