from datetime import datetime

import pytest

from src.chat.replyer.maisaka_generator_base import BaseMaisakaReplyGenerator
from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.config.config import global_config
from src.maisaka.context.message_adapter import format_speaker_content
from src.maisaka.context.messages import SessionBackedMessage


class _DummyLLMClient:
    def __init__(self, *args, **kwargs) -> None:
        del args
        del kwargs


def _build_generator() -> BaseMaisakaReplyGenerator:
    return BaseMaisakaReplyGenerator(
        chat_stream=None,
        request_type="test.replyer",
        llm_client_cls=_DummyLLMClient,
        load_prompt_func=lambda *args, **kwargs: "",
        enable_visual_message=False,
        replyer_mode="text",
    )


def _build_guided_reply_message(content: str) -> SessionBackedMessage:
    return SessionBackedMessage(
        raw_message=MessageSequence([TextComponent(content)]),
        visible_text=format_speaker_content("麦麦", content, datetime.now()),
        timestamp=datetime.now(),
        source_kind="guided_reply",
    )


def test_select_reply_style_replaces_stale_catchphrase_distribution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        global_config.personality,
        "reply_style",
        (
            "默认只说 1 到 2 句，尽量短，单句不超过一个逗号；只在必要时长篇大论。"
            "少解释、少总结、少套话。语气可以可爱、俏皮、会卖萌。"
            "一半的对话中带有口癖，带有口癖的对话中默认使用desuwa；"
            "desuno比 desuwa 稍微多一点追问感、确认感，比如“是这样吗，desuno？”；"
            "teyo更像轻微强调或带一点催促，比如“请别这样说，teyo”；"
            "maa相当于“嘛”或“怎么说呢“；"
        ),
    )

    reply_style = BaseMaisakaReplyGenerator._select_reply_style()

    assert "一半的对话中带有口癖" not in reply_style
    assert "句尾时不时加上 desuwa" in reply_style
    assert "也可偶尔用 desuno" in reply_style
    assert "整条最多一次" in reply_style
    assert "如果上一条你自己的消息已经用了口癖" in reply_style


def test_select_reply_style_deduplicates_current_catchphrase_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        global_config.personality,
        "reply_style",
        (
            "默认只说 1 到 2 句，尽量短，单句不超过一个逗号；只在必要时长篇大论。"
            "句尾时不时加上desuwa，也可偶尔用desuno、teyo、maa，但不要每句都加；"
        ),
    )

    reply_style = BaseMaisakaReplyGenerator._select_reply_style()

    assert reply_style.count("句尾时不时加上 desuwa") == 1
    assert reply_style.count("如果上一条你自己的消息已经用了口癖") == 1


def test_build_recent_catchphrase_requirement_blocks_when_latest_self_reply_used_catchphrase() -> None:
    generator = _build_generator()
    chat_history = [
        _build_guided_reply_message("下一句正常一点"),
        _build_guided_reply_message("先这样吧 desuwa"),
    ]

    requirement = generator._build_recent_catchphrase_requirement(chat_history)

    assert "这条不要再用口癖" in requirement


def test_build_recent_catchphrase_requirement_stays_empty_when_only_older_reply_used_catchphrase() -> None:
    generator = _build_generator()
    chat_history = [
        _build_guided_reply_message("更早之前说过 desuwa"),
        _build_guided_reply_message("下一句正常一点"),
    ]

    requirement = generator._build_recent_catchphrase_requirement(chat_history)

    assert requirement == ""


def test_build_reply_requirements_includes_planner_reply_guide() -> None:
    requirement = BaseMaisakaReplyGenerator._build_reply_requirements(
        "补一句要简短自然",
        [],
        {"reply_guide": "先回答 A-SOUL 的基础信息，再解释鲤鱼姐是 Liyuu。"},
    )

    assert "【额外回复要求】" in requirement
    assert "【Planner回复指引】" in requirement
    assert "先回答 A-SOUL 的基础信息" in requirement
