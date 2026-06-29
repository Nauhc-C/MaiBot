from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types


PLUGIN_PATH = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "context_injector_plugin"
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

    spec = importlib.util.spec_from_file_location("context_injector_plugin_test_module", PLUGIN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_plugin(module):
    plugin = module.ContextInjectorPlugin()
    plugin.config = module.ContextInjectorPluginConfig()
    plugin.config.plugin = module.PluginSectionConfig()
    plugin.config.matching = module.MatchingConfig()
    plugin.config.matching.recent_user_message_limit = 8
    plugin.config.rules = []
    return plugin


def _rule(
    module,
    *,
    name: str = "初华当前处境",
    keywords: list[str] | None = None,
    context: str = "三角初华现在正在和祥子住在一起，祥子睡阁楼。",
    enabled: bool = True,
    inject_to_planner: bool = True,
    inject_to_replyer: bool = True,
):
    rule = module.ContextInjectionRule()
    rule.enabled = enabled
    rule.name = name
    rule.keywords = keywords or ["初华", "三角初华"]
    rule.context = context
    rule.inject_to_planner = inject_to_planner
    rule.inject_to_replyer = inject_to_replyer
    return rule


def _messages(*texts: str):
    messages = [{"role": "system", "content": "system prompt"}]
    for text in texts:
        messages.append({"role": "user", "content": text})
    return messages


def test_latest_window_hit_builds_injection_block() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [_rule(module)]

    injection = plugin._prepare_injection_text(_messages("初华最近怎么样？"), "session-1", "planner")

    assert "【当前对话背景】" in injection
    assert "初华当前处境" in injection
    assert "祥子睡阁楼" in injection


def test_disabled_rule_is_ignored() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [_rule(module, enabled=False)]

    injection = plugin._prepare_injection_text(_messages("初华最近怎么样？"), "session-1", "planner")

    assert injection == ""


def test_multiple_rules_are_merged() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [
        _rule(module, name="初华当前处境", keywords=["初华"], context="初华住在祥子家。"),
        _rule(module, name="祥子住处", keywords=["祥子"], context="祥子睡阁楼。"),
    ]

    injection = plugin._prepare_injection_text(_messages("初华和祥子在做什么？"), "session-1", "planner")

    assert "- 初华当前处境：初华住在祥子家。" in injection
    assert "- 祥子住处：祥子睡阁楼。" in injection


def test_metadata_user_messages_do_not_participate_in_matching() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [_rule(module)]

    messages = _messages(
        "当前时间：2026-06-29 12:00:00",
        "【人物画像-内部参考】初华",
        "<system-reminder>初华</system-reminder>",
        "【当前对话背景】\n- 初华当前处境：三角初华现在正在和祥子住在一起。",
    )

    injection = plugin._prepare_injection_text(messages, "session-1", "planner")

    assert injection == ""


def test_dedupe_injects_once_resets_and_injects_again() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [_rule(module)]

    first = plugin._prepare_injection_text(_messages("初华最近怎么样？"), "session-1", "planner")
    second = plugin._prepare_injection_text(_messages("继续说初华吧"), "session-1", "planner")
    reset = plugin._prepare_injection_text(_messages("说说别的"), "session-1", "planner")
    third = plugin._prepare_injection_text(_messages("初华又出现了"), "session-1", "planner")

    assert first
    assert second == ""
    assert reset == ""
    assert third


def test_planner_claim_prevents_replyer_double_injection() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [_rule(module)]
    messages = _messages("初华最近怎么样？")

    planner = plugin._prepare_injection_text(messages, "session-1", "planner")
    replyer = plugin._prepare_injection_text(messages, "session-1", "replyer")

    assert planner
    assert replyer == ""


def test_replyer_injects_if_planner_did_not_claim() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [_rule(module, inject_to_planner=False, inject_to_replyer=True)]
    messages = _messages("初华最近怎么样？")

    planner = plugin._prepare_injection_text(messages, "session-1", "planner")
    replyer = plugin._prepare_injection_text(messages, "session-1", "replyer")

    assert planner == ""
    assert replyer


def test_planner_hook_returns_modified_messages() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [_rule(module)]

    result = asyncio.run(
        plugin.inject_context_before_planner(
            messages=_messages("初华最近怎么样？"),
            session_id="session-1",
        )
    )

    assert result["action"] == "continue"
    modified_messages = result["modified_kwargs"]["messages"]
    assert modified_messages[-1]["role"] == "user"
    assert "【当前对话背景】" in modified_messages[-1]["content"]


def test_replyer_hook_returns_modified_messages() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [_rule(module)]

    result = asyncio.run(
        plugin.inject_context_before_replyer_model(
            messages=_messages("初华最近怎么样？"),
            session_id="session-1",
        )
    )

    assert result["action"] == "continue"
    modified_messages = result["modified_kwargs"]["messages"]
    assert modified_messages[-1]["role"] == "user"
    assert "【当前对话背景】" in modified_messages[-1]["content"]


def test_empty_messages_invalid_config_and_missing_session_continue() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.rules = [_rule(module)]

    assert asyncio.run(plugin.inject_context_before_planner(messages=[], session_id="session-1")) == {"action": "continue"}
    assert asyncio.run(plugin.inject_context_before_planner(messages=_messages("初华"), session_id="")) == {"action": "continue"}

    plugin.config = types.SimpleNamespace(plugin=object())
    assert asyncio.run(plugin.inject_context_before_planner(messages=_messages("初华"), session_id="session-1")) == {
        "action": "continue"
    }
