from src.chat.utils import utils as chat_utils


def test_default_reply_pool_excludes_rude_short_replies(monkeypatch) -> None:
    """默认短回复池不应包含明显失礼的兜底文案。"""

    captured_choices: dict[str, list[str]] = {}

    def fake_choice(choices: list[str]) -> str:
        captured_choices["items"] = list(choices)
        return choices[0]

    monkeypatch.setattr(chat_utils.random, "choice", fake_choice)

    chat_utils._get_random_default_reply()

    assert "不晓得" not in captured_choices["items"]
    assert "懒得说" not in captured_choices["items"]


def test_splitter_does_not_merge_across_newlines(monkeypatch) -> None:
    """换行应作为硬分段，避免随机合并后把多行文本作为一条消息发送。"""

    monkeypatch.setattr(chat_utils.random, "random", lambda: 0.0)

    segments = chat_utils.split_into_sentences_w_remove_punctuation("我云端的\n\n你拔个锤子")

    assert segments == ["我云端的", "你拔个锤子"]
    assert all("\n" not in segment and "\r" not in segment for segment in segments)


def test_splitter_normalizes_residual_newlines_inside_segment(monkeypatch) -> None:
    """即使换行没有成为分隔点，最终片段里也不应残留实际换行。"""

    monkeypatch.setattr(chat_utils.random, "random", lambda: 1.0)

    segments = chat_utils.split_into_sentences_w_remove_punctuation('"第一行\n第二行"')

    assert segments == ['"第一行 第二行"']


def test_splitter_keeps_dash_adjacent_spaces(monkeypatch) -> None:
    """空格相邻短横线或破折号时不应拆分，避免命令参数和说明文本被切开。"""

    monkeypatch.setattr(chat_utils.random, "random", lambda: 1.0)

    assert chat_utils.split_into_sentences_w_remove_punctuation("pip install -r requirements.txt") == [
        "pip install -r requirements.txt"
    ]
    assert chat_utils.split_into_sentences_w_remove_punctuation("参数 - 值") == ["参数 - 值"]
    assert chat_utils.split_into_sentences_w_remove_punctuation("参数 —— 值") == ["参数 —— 值"]
    assert chat_utils.split_into_sentences_w_remove_punctuation("参数 — 值") == ["参数 — 值"]


def test_splitter_does_not_split_comma_delimited_description(monkeypatch) -> None:
    """逗号罗列型描述不应被切碎成大量短句。"""

    monkeypatch.setattr(chat_utils.random, "random", lambda: 1.0)

    text = "大小姐气质的少女，蓝灰色中长发，发尾微卷，冷色调眼睛，五官端正精致，神情克制冷淡，带一点疏离感，气质高雅，衣着考究，日系动画风，细腻光影，干净背景 desuwa"

    assert chat_utils.split_into_sentences_w_remove_punctuation(text) == [text]


def test_splitter_keeps_long_sync_sentence_as_single_segment(monkeypatch) -> None:
    """长句描述在没有稳定句边界时应尽量保持为单段。"""

    monkeypatch.setattr(chat_utils.random, "random", lambda: 1.0)

    text = (
        "可以把那个键做成“强行同步”呀，按下去不是让她爱上你，而是暂时把她的动作和心意拉到你想要的频率，"
        "所以boss会立刻变得特别配合、特别亲近，关卡也会突然很好过desuwa\n\n"
        "但每按一次，关卡里的细节就更不自然一点，比如她帮你帮得太准、停顿太甜、连她平时不会做的动作都做出来，"
        "最后让玩家自己意识到“这不是她了”，这样收尾到不按那个键才是真正的爱，就会很顺呢"
    )

    assert chat_utils.split_into_sentences_w_remove_punctuation(text) == [
        "可以把那个键做成“强行同步”呀，按下去不是让她爱上你，而是暂时把她的动作和心意拉到你想要的频率，所以boss会立刻变得特别配合、特别亲近，关卡也会突然很好过desuwa 但每按一次，关卡里的细节就更不自然一点，比如她帮你帮得太准、停顿太甜、连她平时不会做的动作都做出来，最后让玩家自己意识到“这不是她了”，这样收尾到不按那个键才是真正的爱，就会很顺呢"
    ]


def test_process_llm_response_merges_overflow_instead_of_fallback(monkeypatch) -> None:
    """句子过多时应压缩合并，而不是退回随机默认短句。"""

    monkeypatch.setattr(chat_utils.random, "random", lambda: 1.0)

    original_enable = chat_utils.global_config.response_post_process.enable_response_post_process
    original_splitter_enable = chat_utils.global_config.response_splitter.enable
    original_typo_enable = chat_utils.global_config.chinese_typo.enable
    original_max_sentence_num = chat_utils.global_config.response_splitter.max_sentence_num
    original_max_split_num = chat_utils.global_config.response_splitter.max_split_num
    original_overflow_return_all = chat_utils.global_config.response_splitter.enable_overflow_return_all

    try:
        chat_utils.global_config.response_post_process.enable_response_post_process = True
        chat_utils.global_config.response_splitter.enable = True
        chat_utils.global_config.chinese_typo.enable = False
        chat_utils.global_config.response_splitter.max_sentence_num = 3
        chat_utils.global_config.response_splitter.max_split_num = 2
        chat_utils.global_config.response_splitter.enable_overflow_return_all = False

        segments = chat_utils.process_llm_response("一。二。三。四。五。")

        assert segments == ["一二三", "四五"]
        assert segments != ["不晓得"]
        assert segments != ["懒得说"]
    finally:
        chat_utils.global_config.response_post_process.enable_response_post_process = original_enable
        chat_utils.global_config.response_splitter.enable = original_splitter_enable
        chat_utils.global_config.chinese_typo.enable = original_typo_enable
        chat_utils.global_config.response_splitter.max_sentence_num = original_max_sentence_num
        chat_utils.global_config.response_splitter.max_split_num = original_max_split_num
        chat_utils.global_config.response_splitter.enable_overflow_return_all = original_overflow_return_all
