from datetime import datetime

from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.chat.replyer.maisaka_generator_base import BaseMaisakaReplyGenerator
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
