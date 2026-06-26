from datetime import datetime
from types import SimpleNamespace

from src.maisaka.context.planner_messages import (
    build_planner_prefix,
    build_planner_user_prefix_from_session_message,
)


def test_build_planner_prefix_marks_self_message_when_enabled() -> None:
    prefix = build_planner_prefix(
        timestamp=datetime(2026, 6, 13, 1, 9, 30),
        user_name="呢猫",
        message_id="1316095995",
        is_self_message=True,
    )

    assert 'is_self_message="true"' in prefix


def test_build_planner_prefix_omits_self_message_mark_by_default() -> None:
    prefix = build_planner_prefix(
        timestamp=datetime(2026, 6, 13, 1, 9, 30),
        user_name="Luft",
        message_id="-1470070102",
    )

    assert 'is_self_message="true"' not in prefix


def test_build_planner_user_prefix_prefers_group_card_for_user_name() -> None:
    message = SimpleNamespace(
        timestamp=datetime(2026, 6, 13, 1, 9, 30),
        message_id="114514",
        session_id="group:1919810",
        is_notify=False,
        raw_message=SimpleNamespace(components=[]),
        message_info=SimpleNamespace(
            user_info=SimpleNamespace(
                user_cardname="群名片",
                user_nickname="QQ昵称",
                user_id="12345678",
            )
        ),
    )

    prefix = build_planner_user_prefix_from_session_message(message)

    assert 'user="群名片"' in prefix
    assert 'group_card="群名片"' in prefix
