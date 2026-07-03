from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import asyncio
import importlib.util
import json
import pytest
import sys
import types


PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "sakiko_bilinote_watcher_plugin"
PLUGIN_PATH = PLUGIN_DIR / "plugin.py"


class FakeLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        del kwargs
        self.records.append(("debug", message % args if args else message))

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        del kwargs
        self.records.append(("info", message % args if args else message))

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        del kwargs
        self.records.append(("warning", message % args if args else message))

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        del kwargs
        self.records.append(("error", message % args if args else message))


class FakeSend:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def text(self, message: str, stream_id: str) -> bool:
        self.messages.append((stream_id, message))
        return True


class FakeLLM:
    def __init__(self, response: str = "小祥看完啦，重点是这个视频在讲测试内容。继续聊哪段都可以。") -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {"success": True, "response": self.response}


class FakeConfig:
    def __init__(self) -> None:
        self.values = {
            "bot.nickname": "小祥",
            "personality.personality": "认真但会撒娇",
            "personality.reply_style": "简短自然",
        }

    async def get(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)


class FakeContext:
    def __init__(self) -> None:
        self.send = FakeSend()
        self.llm = FakeLLM()
        self.config = FakeConfig()
        self.logger = FakeLogger()
        self.capability_calls: list[tuple[str, dict[str, Any]]] = []

    async def call_capability(self, capability: str, **kwargs: Any) -> dict[str, Any]:
        self.capability_calls.append((capability, kwargs))
        if capability == "send.text":
            return {"success": True}
        return {"success": False}


def _load_plugin_module():
    original_sdk = sys.modules.get("maibot_sdk")
    original_sdk_types = sys.modules.get("maibot_sdk.types")
    fake_sdk = types.ModuleType("maibot_sdk")
    fake_sdk_types = types.ModuleType("maibot_sdk.types")

    def fake_field(*args: Any, **kwargs: Any) -> Any:
        del args
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        return kwargs.get("default")

    class FakePluginConfigBase:
        pass

    class FakeMaiBotPlugin:
        def __init__(self) -> None:
            self.config = None
            self.ctx = None

    def fake_decorator(*args: Any, **kwargs: Any):
        del args, kwargs

        def decorator(func):
            return func

        return decorator

    class FakeEventType:
        ON_MESSAGE = "on_message"

    class FakeHookMode:
        OBSERVE = "observe"
        BLOCKING = "blocking"

    class FakeHookOrder:
        NORMAL = "normal"

    class FakeErrorPolicy:
        SKIP = "skip"

    fake_sdk.EventHandler = fake_decorator
    fake_sdk.Field = fake_field
    fake_sdk.HookHandler = fake_decorator
    fake_sdk.MaiBotPlugin = FakeMaiBotPlugin
    fake_sdk.PluginConfigBase = FakePluginConfigBase
    fake_sdk_types.ErrorPolicy = FakeErrorPolicy
    fake_sdk_types.EventType = FakeEventType
    fake_sdk_types.HookMode = FakeHookMode
    fake_sdk_types.HookOrder = FakeHookOrder

    sys.modules["maibot_sdk"] = fake_sdk
    sys.modules["maibot_sdk.types"] = fake_sdk_types

    spec = importlib.util.spec_from_file_location("sakiko_bilinote_watcher_plugin_test_module", PLUGIN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        if original_sdk is None:
            sys.modules.pop("maibot_sdk", None)
        else:
            sys.modules["maibot_sdk"] = original_sdk
        if original_sdk_types is None:
            sys.modules.pop("maibot_sdk.types", None)
        else:
            sys.modules["maibot_sdk.types"] = original_sdk_types
    return module


def _build_plugin(module, tmp_path: Path):
    plugin = module.SakikoBiliNoteWatcherPlugin()
    plugin.config = module.SakikoBiliNoteWatcherConfig()
    plugin.ctx = FakeContext()
    plugin._quota_state_path = tmp_path / "quota_state.json"
    return plugin


def _private_message(text: str, message_id: str = "private-1") -> dict[str, Any]:
    return {
        "message_id": message_id,
        "processed_plain_text": text,
        "session_id": "private-stream",
        "message_info": {"group_info": None},
    }


def _group_message(text: str, message_id: str = "group-1") -> dict[str, Any]:
    return {
        "message_id": message_id,
        "processed_plain_text": text,
        "session_id": "group-stream",
        "message_info": {"group_info": {"group_id": "10001", "group_name": "测试群"}},
    }


async def _capture_enqueued(plugin):
    queued = []

    async def fake_enqueue(request):
        queued.append(request)
        return True

    plugin._enqueue_watch_request = fake_enqueue
    return queued


def test_extract_bilibili_urls_dedupes_and_normalizes() -> None:
    module = _load_plugin_module()

    urls = module.extract_bilibili_urls(
        "看看 b23.tv/abc123?share=1，和 https://m.bilibili.com/video/BV1xx411c7mD?p=1&spm_id_from=333。"
        "重复一下 https://www.bilibili.com/video/BV1xx411c7mD/?spm_id_from=444&p=1"
    )

    assert urls == [
        "https://b23.tv/abc123",
        "https://www.bilibili.com/video/BV1xx411c7mD/?p=1",
    ]


def test_private_message_enqueues_all_unique_urls(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    queued = asyncio.run(_capture_enqueued(plugin))

    asyncio.run(
        plugin._handle_incoming_message(
            message=_private_message(
                "https://www.bilibili.com/video/BV111 和 b23.tv/xyz，再来一次 b23.tv/xyz"
            )
        )
    )

    assert [request.url for request in queued] == [
        "https://www.bilibili.com/video/BV111/",
        "https://b23.tv/xyz",
    ]
    assert all(request.stream_id == "private-stream" for request in queued)
    assert all(not request.is_group for request in queued)


def test_hook_aborts_private_bilibili_link(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    queued = asyncio.run(_capture_enqueued(plugin))

    result = asyncio.run(
        plugin.handle_before_main_reply(
            message=_private_message("https://www.bilibili.com/video/BV111", "private-hook")
        )
    )

    assert result == {"action": "abort"}
    assert [request.url for request in queued] == ["https://www.bilibili.com/video/BV111/"]


def test_hook_continues_without_bilibili_link(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    queued = asyncio.run(_capture_enqueued(plugin))

    result = asyncio.run(plugin.handle_before_main_reply(message=_private_message("普通聊天", "plain-hook")))

    assert result == {"action": "continue"}
    assert queued == []


def test_group_explicit_request_bypasses_sample_and_consumes_quota(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    plugin._random_source = SimpleNamespace(random=lambda: 0.99)
    queued = asyncio.run(_capture_enqueued(plugin))

    asyncio.run(
        plugin._handle_incoming_message(
            message=_group_message("小祥看这个 https://www.bilibili.com/video/BV222", "group-explicit")
        )
    )

    assert len(queued) == 1
    assert queued[0].explicit is True
    assert json.loads(plugin._quota_state_path.read_text(encoding="utf-8"))["count"] == 1


def test_group_passive_link_uses_random_sample(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    random_values = iter([0.2, 0.05])
    plugin._random_source = SimpleNamespace(random=lambda: next(random_values))
    queued = asyncio.run(_capture_enqueued(plugin))

    skipped = asyncio.run(
        plugin._handle_incoming_message(
            message=_group_message("路过一个 https://www.bilibili.com/video/BV333", "group-passive-skip")
        )
    )
    sampled = asyncio.run(
        plugin._handle_incoming_message(
            message=_group_message("路过第二个 https://www.bilibili.com/video/BV444", "group-passive-hit")
        )
    )

    assert skipped is True
    assert sampled is True
    assert [request.url for request in queued] == ["https://www.bilibili.com/video/BV444/"]


def test_reply_target_link_is_ignored_when_current_text_has_no_link(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    queued = asyncio.run(_capture_enqueued(plugin))
    message = _private_message(
        "[回复了某人的消息: https://www.bilibili.com/video/BVOLD] 普通聊天",
        "reply-link-only",
    )
    message["raw_message"] = [
        {"type": "reply", "data": {"target_message_content": "https://www.bilibili.com/video/BVOLD"}},
        {"type": "text", "data": "普通聊天"},
    ]

    result = asyncio.run(plugin.handle_before_main_reply(message=message))

    assert result == {"action": "continue"}
    assert queued == []


def test_raw_text_link_is_used_even_with_reply_component(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    queued = asyncio.run(_capture_enqueued(plugin))
    message = _private_message("processed 里没有真实正文", "reply-with-current-link")
    message["raw_message"] = [
        {"type": "reply", "data": {"target_message_content": "普通旧消息"}},
        {
            "type": "text",
            "data": "小祥看这个 https://www.bilibili.com/video/BVNEW/?spm_id_from=333",
        },
    ]

    result = asyncio.run(plugin.handle_before_main_reply(message=message))

    assert result == {"action": "abort"}
    assert [request.url for request in queued] == ["https://www.bilibili.com/video/BVNEW/"]


def test_group_quota_blocks_and_sends_cute_message(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    plugin.config.group_policy.daily_quota = 1
    plugin._save_quota_state({"date": plugin._today(), "count": 1})
    queued = asyncio.run(_capture_enqueued(plugin))

    asyncio.run(
        plugin._handle_incoming_message(
            message=_group_message("小祥看这个 https://www.bilibili.com/video/BV555", "group-quota-full")
        )
    )

    assert queued == []
    assert plugin.ctx.capability_calls
    assert plugin.ctx.capability_calls[0][0] == "send.text"
    assert "流量" in plugin.ctx.capability_calls[0][1]["text"]


def test_group_quota_resets_by_local_date(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    plugin._save_quota_state({"date": "2026-07-01", "count": 10})
    plugin._today = lambda: "2026-07-02"

    assert plugin._has_group_quota() is True
    plugin._consume_group_quota()

    state = json.loads(plugin._quota_state_path.read_text(encoding="utf-8"))
    assert state == {"date": "2026-07-02", "count": 1}


def test_same_message_id_is_deduped(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    queued = asyncio.run(_capture_enqueued(plugin))
    message = _private_message("https://www.bilibili.com/video/BV666", "same-message")

    asyncio.run(plugin._handle_incoming_message(message=message))
    asyncio.run(plugin._handle_incoming_message(message=message))

    assert len(queued) == 1


def test_process_watch_request_uses_fake_transcriber_and_llm(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)

    async def fake_transcribe(url: str) -> dict[str, Any]:
        return {
            "title": "测试视频",
            "source_url": url,
            "full_text": "第一段内容。第二段内容。",
        }

    plugin._transcribe_url = fake_transcribe
    request = module.WatchRequest(
        url="https://www.bilibili.com/video/BV777",
        stream_id="private-stream",
        is_group=False,
        explicit=True,
        source_text="看这个",
    )

    asyncio.run(plugin._process_watch_request(request))

    assert plugin.ctx.llm.calls
    assert "测试视频" in plugin.ctx.llm.calls[0]["prompt"]
    states = plugin._get_visible_watch_states("private-stream")
    assert len(states) == 1
    assert states[0].status == "done"
    assert states[0].title == "测试视频"
    assert "测试内容" in states[0].summary
    assert plugin.ctx.capability_calls == [
        (
            "send.text",
            {
                "text": "小祥看完啦，重点是这个视频在讲测试内容。继续聊哪段都可以。",
                "stream_id": "private-stream",
                "typing": False,
                "storage_message": True,
                "sync_to_maisaka_history": True,
                "maisaka_source_kind": "sakiko_bilinote_summary",
            },
        )
    ]


def test_prepare_watch_request_expands_b23_short_url(tmp_path: Path, monkeypatch) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            del exc_type, exc, tb
            return False

        def geturl(self) -> str:
            return "https://m.bilibili.com/video/BVSHORT123?p=2&share_source=copy_web"

    calls: list[tuple[str, float]] = []

    def fake_urlopen(request, timeout: float):
        calls.append((request.full_url, timeout))
        return FakeResponse()

    monkeypatch.setattr(module, "urlopen", fake_urlopen)
    request = module.WatchRequest(
        url="https://b23.tv/abc123",
        stream_id="private-stream",
        is_group=False,
        explicit=True,
        source_text="看这个",
        request_id="watch-short",
    )

    prepared = asyncio.run(plugin._prepare_watch_request(request))

    assert prepared.url == "https://www.bilibili.com/video/BVSHORT123/?p=2"
    assert calls == [("https://b23.tv/abc123", 10.0)]


def test_worker_loop_failure_marks_state_without_sending_fixed_reply(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    request = module.WatchRequest(
        url="https://www.bilibili.com/video/BVFAIL001/",
        stream_id="private-stream",
        is_group=False,
        explicit=True,
        source_text="看这个",
        request_id="watch-failure",
    )

    async def exercise_worker() -> None:
        plugin._queue = asyncio.Queue(maxsize=plugin._queue_size())
        await plugin._queue.put(request)

        async def fake_process(_request) -> None:
            raise RuntimeError("boom")

        plugin._process_watch_request = fake_process
        worker = asyncio.create_task(plugin._worker_loop())
        await plugin._queue.join()
        worker.cancel()
        with pytest.raises(asyncio.CancelledError):
            await worker

    asyncio.run(exercise_worker())

    states = plugin._get_visible_watch_states("private-stream")
    assert len(states) == 1
    assert states[0].status == "failed"
    assert "稍后再发一次" in states[0].error_hint
    assert plugin.ctx.capability_calls == []


def test_active_watch_state_is_injected_into_planner_and_replyer(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    request = module.WatchRequest(
        url="https://www.bilibili.com/video/BV999",
        stream_id="private-stream",
        is_group=False,
        explicit=True,
        source_text="小祥看这个",
        message_id="active-watch",
        request_id="watch-active",
    )
    plugin._upsert_watch_state(request, status="transcribing")

    planner_result = asyncio.run(
        plugin.inject_planner_watch_context(
            messages=[{"role": "user", "content": "看到没"}],
            session_id="private-stream",
        )
    )
    planner_messages = planner_result["modified_kwargs"]["messages"]
    planner_context = planner_messages[-1]["content"]
    assert "Bilibili 视频观看状态" in planner_context
    assert "正在看这个 Bilibili 视频" in planner_context
    assert "不要假装已经看完" in planner_context

    replyer_result = asyncio.run(
        plugin.inject_replyer_watch_context(
            session_id="private-stream",
            extra_prompt="原有提示",
            selected_expression_ids=[1],
            reply_tool_args={"foo": "bar"},
        )
    )
    modified = replyer_result["modified_kwargs"]
    assert modified["extra_prompt"].startswith("原有提示")
    assert "正在看这个 Bilibili 视频" in modified["extra_prompt"]
    assert modified["selected_expression_ids"] == [1]
    assert modified["reply_tool_args"] == {"foo": "bar"}


def test_done_watch_state_tells_bot_not_to_deny_watching(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    request = module.WatchRequest(
        url="https://www.bilibili.com/video/BVDONE",
        stream_id="private-stream",
        is_group=False,
        explicit=True,
        source_text="小祥看这个",
        request_id="watch-done",
    )
    plugin._upsert_watch_state(
        request,
        status="done",
        title="卡比龙包装设计",
        source_url=request.url,
        summary="小祥看完啦，重点是包装像艺术品，也聊到展示方式。",
    )

    context = plugin._build_watch_context_prompt("private-stream")

    assert "刚刚已经看完并发过小祥摘要" in context
    assert "不要否认自己看过" in context
    assert "卡比龙包装设计" in context
    assert "包装像艺术品" in context


def test_send_text_falls_back_when_capability_is_missing(tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    plugin.ctx.call_capability = None

    asyncio.run(plugin._send_text("fallback message", "private-stream"))

    assert plugin.ctx.send.messages == [("private-stream", "fallback message")]


def test_transcribe_blocking_builds_bilinote_command(tmp_path: Path, monkeypatch) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module, tmp_path)
    script = tmp_path / "bilinote_transcribe.py"
    script.write_text("print('unused')", encoding="utf-8")
    plugin.config.bilinote.script_path = str(script)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"title": "OK", "full_text": "done"}, ensure_ascii=False),
            stderr="",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = plugin._transcribe_url_blocking("https://www.bilibili.com/video/BV888")

    assert payload["full_text"] == "done"
    command = calls[0][0]
    assert command[0] == sys.executable
    assert str(script) in command
    assert "--format" in command
    assert "json" in command
    assert "--quiet" in command
    assert calls[0][1]["encoding"] == "utf-8"
