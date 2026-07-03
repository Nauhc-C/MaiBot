from datetime import datetime
from pathlib import Path

from src.chat.replyer.local_mai_replyer import LOCAL_MAI_REPLYER_SYSTEM_PROMPT
from src.chat.replyer.maisaka_generator_base import BaseMaisakaReplyGenerator
from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.llm_models.payload_content.message import RoleType
from src.maisaka.context.messages import AssistantMessage, SessionBackedMessage


def test_build_reply_requirements_includes_planner_reply_guide() -> None:
    requirement = BaseMaisakaReplyGenerator._build_reply_requirements(
        "补一句要简短自然",
        [],
        {"reply_guide": "先回答 A-SOUL 的基础信息，再解释鲤鱼姐是 Liyuu。"},
    )

    assert "【额外回复要求】" in requirement
    assert "【Planner回复指引】" in requirement
    assert "先回答 A-SOUL 的基础信息" in requirement
    assert "【引用回复策略】" in requirement


def test_replyer_prompts_preserve_key_facts_and_attitude() -> None:
    project_root = Path(__file__).resolve().parents[2]

    zh_prompt = (project_root / "prompts" / "zh-CN" / "maisaka_replyer.prompt").read_text(encoding="utf-8")
    en_prompt = (project_root / "prompts" / "en-US" / "maisaka_replyer.prompt").read_text(encoding="utf-8")
    ja_prompt = (project_root / "prompts" / "ja-JP" / "maisaka_replyer.prompt").read_text(encoding="utf-8")

    assert "关键事实" in zh_prompt
    assert "实事求是" in zh_prompt
    assert "当前态度" in zh_prompt
    assert "Key facts" in en_prompt
    assert "current attitude" in en_prompt
    assert "重要な事実" in ja_prompt
    assert "現在の態度" in ja_prompt
    assert "关键事实" in LOCAL_MAI_REPLYER_SYSTEM_PROMPT
    assert "空泛情绪" in LOCAL_MAI_REPLYER_SYSTEM_PROMPT


def test_build_reply_requirements_sets_explicit_quote_policy() -> None:
    requirement = BaseMaisakaReplyGenerator._build_reply_requirements("", [], {})

    assert "set_quote=true" in requirement
    assert "set_quote=false" in requirement


class _DummyReplyGenerator(BaseMaisakaReplyGenerator):
    def __init__(self) -> None:
        super().__init__(
            chat_stream=None,
            request_type="maisaka.replyer",
            llm_client_cls=lambda **kwargs: object(),
            load_prompt_func=lambda *args, **kwargs: "",
            enable_visual_message=False,
            replyer_mode="text",
        )


def test_build_history_messages_treats_guided_reply_as_assistant() -> None:
    generator = _DummyReplyGenerator()
    message = SessionBackedMessage(
        raw_message=MessageSequence([TextComponent("[麦麦]好的 desuwa")]),
        visible_text="[麦麦]好的 desuwa",
        timestamp=datetime.now(),
        source_kind="guided_reply",
    )

    messages = generator._build_history_messages([message], enable_visual_message=False)

    assert len(messages) == 1
    assert messages[0].role == RoleType.Assistant
    assert messages[0].get_text_content() == "好的 desuwa"


def test_build_history_messages_keeps_assistant_message_visible() -> None:
    generator = _DummyReplyGenerator()
    message = AssistantMessage(content="这是内部 assistant 消息", timestamp=datetime.now())

    messages = generator._build_history_messages([message], enable_visual_message=False)

    assert len(messages) == 1
    assert messages[0].role == RoleType.Assistant
    assert messages[0].get_text_content() == "这是内部 assistant 消息"
