"""校验 Hook 载荷图片占位符的脱敏与还原往返。"""

import pytest

from src.llm_models.payload_content.message import ImageMessagePart, Message, RoleType, TextMessagePart
from src.plugin_runtime.hook_payloads import (
    IMAGE_REF_KEY,
    rehydrate_prompt_messages_from_hook,
    serialize_prompt_messages_for_hook,
)

# 一段足够大的伪 base64，用来确认脱敏后载荷不再携带原始图片数据。
_LARGE_IMAGE_BASE64 = "A" * 100_000


def _build_multimodal_messages() -> list[Message]:
    return [
        Message(role=RoleType.System, parts=[TextMessagePart(text="你是助手")]),
        Message(
            role=RoleType.User,
            parts=[
                TextMessagePart(text="看看这张图"),
                ImageMessagePart(image_format="png", image_base64=_LARGE_IMAGE_BASE64),
            ],
        ),
    ]


def test_serialize_elides_image_base64_into_placeholder() -> None:
    serialized, image_ref_store = serialize_prompt_messages_for_hook(_build_multimodal_messages())

    # base64 应只留存在 store 中，序列化结果里不得再出现原始图片数据。
    assert len(image_ref_store) == 1
    assert list(image_ref_store.values())[0] == ("png", _LARGE_IMAGE_BASE64)

    image_content = serialized[1]["content"]
    assert isinstance(image_content, list)
    placeholder = next(item for item in image_content if isinstance(item, dict) and IMAGE_REF_KEY in item)
    assert placeholder["image_format"] == "png"
    assert _LARGE_IMAGE_BASE64 not in repr(serialized)


def test_round_trip_restores_original_image_base64() -> None:
    serialized, image_ref_store = serialize_prompt_messages_for_hook(_build_multimodal_messages())

    restored = rehydrate_prompt_messages_from_hook(serialized, image_ref_store)

    restored_parts = restored[1].parts
    image_part = next(part for part in restored_parts if isinstance(part, ImageMessagePart))
    assert image_part.image_format == "png"
    assert image_part.image_base64 == _LARGE_IMAGE_BASE64


def test_round_trip_preserves_plugin_appended_message() -> None:
    serialized, image_ref_store = serialize_prompt_messages_for_hook(_build_multimodal_messages())

    # 模拟插件在末尾追加一条纯文本参考消息（萌娘百科插件的典型行为）。
    serialized.append({"role": "user", "content": [{"type": "text", "text": "补充参考资料"}]})

    restored = rehydrate_prompt_messages_from_hook(serialized, image_ref_store)

    assert len(restored) == 3
    assert restored[2].role == RoleType.User
    assert restored[2].get_text_content() == "补充参考资料"
    # 原图片仍应被正确还原。
    image_part = next(part for part in restored[1].parts if isinstance(part, ImageMessagePart))
    assert image_part.image_base64 == _LARGE_IMAGE_BASE64


def test_round_trip_allows_plugin_appended_image() -> None:
    serialized, image_ref_store = serialize_prompt_messages_for_hook(_build_multimodal_messages())

    # 插件可自带一张小图（不经过占位符机制），应原样透传并被反序列化。
    serialized.append(
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "缩略图"},
                {"type": "image", "image_format": "jpeg", "image_base64": "BBBB"},
            ],
        }
    )

    restored = rehydrate_prompt_messages_from_hook(serialized, image_ref_store)

    appended_image = next(part for part in restored[2].parts if isinstance(part, ImageMessagePart))
    assert appended_image.normalized_image_format == "jpeg"
    assert appended_image.image_base64 == "BBBB"


def test_unknown_placeholder_reference_raises() -> None:
    serialized, _ = serialize_prompt_messages_for_hook(_build_multimodal_messages())

    # store 为空时，占位符引用无法解析，应显式报错而非静默吞掉。
    with pytest.raises(ValueError, match="未知的图片 ID"):
        rehydrate_prompt_messages_from_hook(serialized, {})
