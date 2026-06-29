from datetime import datetime, timedelta

from src.chat.message_receive.message import SessionMessage
from src.chat.replyer.maisaka_generator_base import BaseMaisakaReplyGenerator
from src.common.data_models.mai_message_data_model import GroupInfo, MessageInfo, UserInfo
from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
from src.maisaka.context.history import DEFAULT_CONTEXT_TIME_WINDOW_MINUTES, filter_history_by_time_window
from src.maisaka.chat_loop_service import MaisakaChatLoopService
from src.maisaka.context.messages import SessionBackedMessage


def _build_session_message(message_id: str, minutes_ago: int, text: str) -> SessionMessage:
    message = SessionMessage(
        message_id=message_id,
        timestamp=datetime.now() - timedelta(minutes=minutes_ago),
        platform="test",
    )
    message.session_id = "session:test"
    message.message_info = MessageInfo(
        user_info=UserInfo(user_id="u1", user_nickname="Alice", user_cardname="Alice"),
        group_info=GroupInfo(group_id="g1", group_name="Group"),
        additional_config={},
    )
    message.raw_message = MessageSequence([TextComponent(text)])
    message.processed_plain_text = text
    return message


def test_filter_history_by_time_window_drops_old_messages() -> None:
    recent = SessionBackedMessage.from_session_message(
        _build_session_message("recent", 10, "最近一条"),
        raw_message=MessageSequence([TextComponent("最近一条")]),
        visible_text="最近一条",
    )
    old = SessionBackedMessage.from_session_message(
        _build_session_message("old", 120, "很久以前"),
        raw_message=MessageSequence([TextComponent("很久以前")]),
        visible_text="很久以前",
    )

    filtered = filter_history_by_time_window([old, recent], time_window_minutes=30)

    assert filtered == [recent]


def test_select_llm_context_messages_applies_time_window_before_selection() -> None:
    recent = SessionBackedMessage.from_session_message(
        _build_session_message("recent", 5, "最近一条"),
        raw_message=MessageSequence([TextComponent("最近一条")]),
        visible_text="最近一条",
    )
    old = SessionBackedMessage.from_session_message(
        _build_session_message("old", 120, "很久以前"),
        raw_message=MessageSequence([TextComponent("很久以前")]),
        visible_text="很久以前",
    )

    selected_history, selection_reason = MaisakaChatLoopService.select_llm_context_messages(
        [old, recent],
        request_kind="planner",
        max_context_size=10,
        time_window_minutes=30,
    )

    assert selected_history == [recent]
    assert "实际发送 1 条消息" in selection_reason


def test_reply_context_window_constant_is_small() -> None:
    assert DEFAULT_CONTEXT_TIME_WINDOW_MINUTES == 30


def test_replyer_base_uses_time_windowed_history_filter() -> None:
    recent = SessionBackedMessage.from_session_message(
        _build_session_message("recent", 5, "最近一条"),
        raw_message=MessageSequence([TextComponent("最近一条")]),
        visible_text="最近一条",
    )
    old = SessionBackedMessage.from_session_message(
        _build_session_message("old", 120, "很久以前"),
        raw_message=MessageSequence([TextComponent("很久以前")]),
        visible_text="很久以前",
    )

    filtered = BaseMaisakaReplyGenerator._filter_replyer_history_by_time_window(
        [old, recent],
        time_window_minutes=DEFAULT_CONTEXT_TIME_WINDOW_MINUTES,
    )

    assert filtered == [recent]
