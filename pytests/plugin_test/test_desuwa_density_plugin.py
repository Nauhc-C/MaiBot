from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
import types


PLUGIN_PATH = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "desuwa_density_plugin"
    / "plugin.py"
)


def _load_plugin_module():
    fake_sdk = types.ModuleType("maibot_sdk")
    fake_sdk_types = types.ModuleType("maibot_sdk.types")

    def fake_field(*args, **kwargs):
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        return kwargs.get("default")

    class FakePluginConfigBase:
        pass

    class FakeMaiBotPlugin:
        def __init__(self) -> None:
            self.config = types.SimpleNamespace()
            self.ctx = None

    def fake_hook_handler(*args, **kwargs):
        del args, kwargs

        def decorator(func):
            return func

        return decorator

    class FakeErrorPolicy:
        SKIP = "skip"

    class FakeHookMode:
        BLOCKING = "blocking"

    class FakeHookOrder:
        NORMAL = "normal"

    fake_sdk.Field = fake_field
    fake_sdk.HookHandler = fake_hook_handler
    fake_sdk.MaiBotPlugin = FakeMaiBotPlugin
    fake_sdk.PluginConfigBase = FakePluginConfigBase
    fake_sdk_types.ErrorPolicy = FakeErrorPolicy
    fake_sdk_types.HookMode = FakeHookMode
    fake_sdk_types.HookOrder = FakeHookOrder

    sys.modules["maibot_sdk"] = fake_sdk
    sys.modules["maibot_sdk.types"] = fake_sdk_types

    spec = importlib.util.spec_from_file_location("desuwa_density_plugin_test_module", PLUGIN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_plugin(module):
    plugin = module.DesuwaDensityPlugin()
    plugin.config = module.DesuwaDensityPluginConfig()
    plugin.ctx = types.SimpleNamespace(
        message=types.SimpleNamespace(get_recent=None),
        logger=types.SimpleNamespace(info=lambda *args, **kwargs: None, warning=lambda *args, **kwargs: None),
        call_capability=None,
        config=types.SimpleNamespace(get=None),
    )
    return plugin


def test_build_frequency_instruction_prefers_desuwa_when_sparse() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    stats = module.CatchphraseStats(
        recent_texts=["今天好热", "真的不想上班", "你先喝水"],
        total_count=3,
        catchphrase_count=0,
        density=0.0,
        last_message_used=False,
        messages_since_last_use=3,
    )

    instruction = plugin._build_frequency_instruction(stats)

    assert "优先考虑补一个轻口癖" in instruction


def test_build_choice_guidance_contains_catchphrase_policy() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)

    instruction = plugin._build_choice_guidance()

    assert "普通收尾优先用 desuwa" in instruction
    assert "轻微追问或确认时用 desuno" in instruction
    assert "轻微强调或带一点催促时才少量用 teyo" in instruction


def test_build_prompt_nudge_returns_empty_when_last_message_used_catchphrase() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    stats = module.CatchphraseStats(
        recent_texts=["上一条已经用了desuwa"],
        total_count=1,
        catchphrase_count=1,
        density=1.0,
        last_message_used=True,
        messages_since_last_use=0,
    )

    instruction = plugin._build_prompt_nudge(stats)

    assert instruction == ""


def test_maybe_patch_response_appends_desuwa_when_sparse() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    stats = module.CatchphraseStats(
        recent_texts=["今天好热", "真的不想上班", "你先喝水"],
        total_count=3,
        catchphrase_count=0,
        density=0.0,
        last_message_used=False,
        messages_since_last_use=4,
    )

    patched = plugin._maybe_patch_response("我这次认真又看了一遍，别哭哭嘛", stats)

    assert patched.endswith("desuwa")


def test_maybe_patch_response_uses_desuno_for_confirmation_when_sparse() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    stats = module.CatchphraseStats(
        recent_texts=["今天好热", "真的不想上班", "你先喝水"],
        total_count=3,
        catchphrase_count=0,
        density=0.0,
        last_message_used=False,
        messages_since_last_use=4,
    )

    patched = plugin._maybe_patch_response("这样就可以了吗？", stats)

    assert patched == "这样就可以了吗，desuno？"


def test_maybe_patch_response_strips_trailing_catchphrase_when_last_message_used() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    stats = module.CatchphraseStats(
        recent_texts=["上一条已经用了desuwa"],
        total_count=1,
        catchphrase_count=1,
        density=1.0,
        last_message_used=True,
        messages_since_last_use=0,
    )

    patched = plugin._maybe_patch_response("那我再看看desuwa", stats)

    assert patched == "那我再看看"


def test_before_request_merges_extra_prompt_with_frequency_instruction() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    captured_kwargs = {}
    now = datetime.now()

    async def fake_get_recent(**kwargs):
        captured_kwargs.update(kwargs)
        return {
            "success": True,
            "messages": [
                {
                    "message_id": "1",
                    "platform": "qq",
                    "message_info": {"user_info": {"user_id": "bot-1"}},
                    "timestamp": (now - timedelta(minutes=3)).isoformat(sep=" "),
                    "processed_plain_text": "今天好热",
                },
                {
                    "message_id": "2",
                    "platform": "qq",
                    "message_info": {"user_info": {"user_id": "user-2"}},
                    "timestamp": (now - timedelta(minutes=2)).isoformat(sep=" "),
                    "processed_plain_text": "真的不想上班",
                },
                {
                    "message_id": "3",
                    "platform": "qq",
                    "message_info": {"user_info": {"user_id": "bot-1"}},
                    "timestamp": (now - timedelta(minutes=1)).isoformat(sep=" "),
                    "processed_plain_text": "你先喝水",
                },
            ],
        }

    async def fake_call_capability(capability, **kwargs):
        if capability == "message.get_recent":
            return await fake_get_recent(**kwargs)
        raise AssertionError(capability)

    async def fake_get_config(key, default=None):
        config_values = {
            "bot.qq_account": "bot-1",
            "bot.platforms": [],
        }
        return config_values.get(key, default)

    plugin.ctx.call_capability = fake_call_capability
    plugin.ctx.config.get = fake_get_config

    result = asyncio.run(
        plugin.regulate_desuwa_before_request(
            session_id="qq_private_DEVELOPER_ACCOUNT_ID",
            request_type="maisaka.replyer",
            task_name="replyer",
            model_name="",
            extra_prompt="先回答问题",
            attempt=1,
            retry_count=0,
            max_retries=3,
            reply_message_id="123",
            reply_reason="",
            selected_expression_ids=[],
            reply_tool_args={},
        )
    )

    assert result["action"] == "continue"
    assert captured_kwargs["chat_id"] == "qq_private_DEVELOPER_ACCOUNT_ID"
    assert captured_kwargs["limit"] >= 16
    assert captured_kwargs["hours"] == plugin.config.density.lookback_hours
    merged_prompt = result["modified_kwargs"]["extra_prompt"]
    assert "先回答问题" in merged_prompt
    assert "普通收尾优先用 desuwa" in merged_prompt
    assert "优先考虑补一个轻口癖" in merged_prompt


def test_before_request_is_silent_when_last_message_used_catchphrase() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    now = datetime.now()

    async def fake_call_capability(capability, **kwargs):
        if capability == "message.get_recent":
            return {
                "success": True,
                "messages": [
                    {
                        "message_id": "1",
                        "platform": "qq",
                        "message_info": {"user_info": {"user_id": "bot-1"}},
                        "timestamp": (now - timedelta(minutes=2)).isoformat(sep=" "),
                        "processed_plain_text": "我刚看完了desuwa",
                    },
                    {
                        "message_id": "2",
                        "platform": "qq",
                        "message_info": {"user_info": {"user_id": "user-2"}},
                        "timestamp": (now - timedelta(minutes=1)).isoformat(sep=" "),
                        "processed_plain_text": "那然后呢",
                    },
                ],
            }
        raise AssertionError(capability)

    async def fake_get_config(key, default=None):
        config_values = {
            "bot.qq_account": "bot-1",
            "bot.platforms": [],
        }
        return config_values.get(key, default)

    plugin.ctx.call_capability = fake_call_capability
    plugin.ctx.config.get = fake_get_config

    result = asyncio.run(
        plugin.regulate_desuwa_before_request(
            session_id="qq_private_DEVELOPER_ACCOUNT_ID",
            request_type="maisaka.replyer",
            task_name="replyer",
            model_name="",
            extra_prompt="先回答问题",
            attempt=1,
            retry_count=0,
            max_retries=3,
            reply_message_id="123",
            reply_reason="",
            selected_expression_ids=[],
            reply_tool_args={},
        )
    )

    assert result == {"action": "continue"}


def test_manifest_declares_config_get_capability() -> None:
    manifest_path = PLUGIN_PATH.with_name("_manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert "config.get" in manifest["capabilities"]
    assert "message.get_recent" in manifest["capabilities"]
