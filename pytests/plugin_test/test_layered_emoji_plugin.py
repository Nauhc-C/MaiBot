from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import random
import sys
import types


PLUGIN_PATH = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "layered_emoji_plugin"
    / "plugin.py"
)


class DummyEmoji:
    def __init__(self, file_hash: str, description: str, query_count: int = 0):
        self.file_hash = file_hash
        self.description = description
        self.emotion = [item.strip() for item in description.split(",") if item.strip()]
        self.query_count = query_count


class FakeSend:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def text(self, message: str, stream_id: str):
        self.messages.append((stream_id, message))
        return True


def _load_plugin_module():
    fake_sdk = types.ModuleType("maibot_sdk")
    fake_sdk_types = types.ModuleType("maibot_sdk.types")

    def fake_field(*args, **kwargs):
        del args
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        return kwargs.get("default")

    class FakePluginConfigBase:
        pass

    class FakeMaiBotPlugin:
        def __init__(self) -> None:
            self.config = types.SimpleNamespace()
            self.ctx = None

        async def on_load(self) -> None:
            pass

        async def on_unload(self) -> None:
            pass

        async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
            pass

    def fake_decorator(*args, **kwargs):
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

    fake_sdk.Command = fake_decorator
    fake_sdk.Field = fake_field
    fake_sdk.HookHandler = fake_decorator
    fake_sdk.MaiBotPlugin = FakeMaiBotPlugin
    fake_sdk.PluginConfigBase = FakePluginConfigBase
    fake_sdk_types.ErrorPolicy = FakeErrorPolicy
    fake_sdk_types.HookMode = FakeHookMode
    fake_sdk_types.HookOrder = FakeHookOrder

    sys.modules["maibot_sdk"] = fake_sdk
    sys.modules["maibot_sdk.types"] = fake_sdk_types

    spec = importlib.util.spec_from_file_location("layered_emoji_plugin_test_module", PLUGIN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _build_plugin(module):
    plugin = module.LayeredEmojiPlugin()
    plugin.config = module.LayeredEmojiPluginConfig()
    plugin.ctx = types.SimpleNamespace(send=FakeSend(), call_capability=None)
    return plugin


def test_plugin_overrides_required_lifecycle_methods() -> None:
    module = _load_plugin_module()

    assert module.LayeredEmojiPlugin.on_load is not module.MaiBotPlugin.on_load
    assert module.LayeredEmojiPlugin.on_unload is not module.MaiBotPlugin.on_unload
    assert module.LayeredEmojiPlugin.on_config_update is not module.MaiBotPlugin.on_config_update


def test_load_layer_catalog_normalizes_layers_and_hashes(tmp_path: Path) -> None:
    module = _load_plugin_module()
    catalog_path = tmp_path / "emoji_layers.toml"
    catalog_path.write_text(
        """
[[layers.items]]
id = "q_xiang"
name = "Q版小祥"
weight = 1.5
enabled_by_default = true

[[layers.items]]
id = "original_xiang"
name = "原图小祥"
weight = 0.8
enabled_by_default = false

[emoji_map]
"ABCDEF" = ["q_xiang", "missing"]
""",
        encoding="utf-8",
    )

    catalog = module.load_layer_catalog(catalog_path)

    assert set(catalog.layers) == {"q_xiang", "original_xiang"}
    assert catalog.layers["q_xiang"].weight == 1.5
    assert catalog.get_layers_for_hash("abcdef") == {"q_xiang"}


def test_choose_emoji_filters_by_selected_layers() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin._catalog = module.EmojiLayerCatalog(
        layers={
            "q_xiang": module.EmojiLayer("q_xiang", "Q版小祥"),
            "original_xiang": module.EmojiLayer("original_xiang", "原图小祥"),
        },
        emoji_layers={
            "q_hash": {"q_xiang"},
            "original_hash": {"original_xiang"},
        },
    )
    plugin.config.layers.default_active_layers = ["q_xiang"]
    plugin.config.layers.include_unclassified = False
    emojis = [
        DummyEmoji("q_hash", "开心"),
        DummyEmoji("original_hash", "开心"),
    ]

    chosen = plugin.choose_emoji(
        emojis,
        stream_id="stream-1",
        requested_emotion="开心",
        random_source=random.Random(3),
    )

    assert chosen.file_hash == "q_hash"


def test_unclassified_emoji_can_be_included_or_excluded() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin._catalog = module.EmojiLayerCatalog(
        layers={"q_xiang": module.EmojiLayer("q_xiang", "Q版小祥")},
        emoji_layers={"q_hash": {"q_xiang"}},
    )
    plugin.config.layers.default_active_layers = ["q_xiang"]
    emojis = [
        DummyEmoji("unclassified_hash", "开心"),
    ]

    plugin.config.layers.include_unclassified = False
    assert plugin.choose_emoji(emojis, stream_id="stream-1", requested_emotion="开心") is None

    plugin.config.layers.include_unclassified = True
    chosen = plugin.choose_emoji(
        emojis,
        stream_id="stream-1",
        requested_emotion="开心",
        random_source=random.Random(1),
    )
    assert chosen.file_hash == "unclassified_hash"


def test_recent_history_softly_penalizes_same_emotion_repeat() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin._catalog = module.EmojiLayerCatalog(
        layers={"q_xiang": module.EmojiLayer("q_xiang", "Q版小祥")},
        emoji_layers={"first": {"q_xiang"}, "second": {"q_xiang"}},
    )
    plugin.config.layers.default_active_layers = ["q_xiang"]
    plugin.config.layers.include_unclassified = False
    plugin.config.layers.random_jitter = 0.0
    first = DummyEmoji("first", "开心")
    second = DummyEmoji("second", "开心")

    before_penalty = plugin._score_emoji(
        first,
        stream_id="stream-1",
        emotion_key="开心",
        target_emotion="开心",
        selected_hash="",
        random_source=random.Random(1),
    )
    plugin._record_recent_choice("stream-1", "开心", "first")
    after_penalty = plugin._score_emoji(
        first,
        stream_id="stream-1",
        emotion_key="开心",
        target_emotion="开心",
        selected_hash="",
        random_source=random.Random(1),
    )
    other_score = plugin._score_emoji(
        second,
        stream_id="stream-1",
        emotion_key="开心",
        target_emotion="开心",
        selected_hash="",
        random_source=random.Random(1),
    )

    assert after_penalty < before_penalty
    assert after_penalty > 0
    assert other_score > after_penalty


def test_after_select_hook_returns_modified_selected_hash(monkeypatch) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin._catalog = module.EmojiLayerCatalog(
        layers={"q_xiang": module.EmojiLayer("q_xiang", "Q版小祥")},
        emoji_layers={"preferred": {"q_xiang"}},
    )
    plugin._catalog_available = True
    plugin.config.layers.default_active_layers = ["q_xiang"]
    plugin.config.layers.include_unclassified = False
    emoji_manager_module = types.ModuleType("src.emoji_system.emoji_manager")
    emoji_manager_module.emoji_manager = types.SimpleNamespace(
        emojis=[
            DummyEmoji("preferred", "开心"),
            DummyEmoji("other", "开心"),
        ]
    )
    monkeypatch.setitem(sys.modules, "src.emoji_system.emoji_manager", emoji_manager_module)

    result = asyncio.run(
        plugin.handle_emoji_after_select(
            stream_id="stream-1",
            requested_emotion="开心",
            selected_emoji_hash="other",
            matched_emotion="开心",
        )
    )

    assert result["action"] == "continue"
    assert result["modified_kwargs"]["selected_emoji_hash"] == "preferred"
    assert result["modified_kwargs"]["stream_id"] == "stream-1"


def test_after_select_hook_keeps_original_when_disabled(monkeypatch) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.plugin.enabled = False
    emoji_manager_module = types.ModuleType("src.emoji_system.emoji_manager")
    emoji_manager_module.emoji_manager = types.SimpleNamespace(emojis=[DummyEmoji("preferred", "开心")])
    monkeypatch.setitem(sys.modules, "src.emoji_system.emoji_manager", emoji_manager_module)

    result = asyncio.run(
        plugin.handle_emoji_after_select(
            stream_id="stream-1",
            requested_emotion="开心",
            selected_emoji_hash="other",
            matched_emotion="开心",
        )
    )

    assert result == {"action": "continue"}


def test_after_select_hook_keeps_original_when_catalog_missing(monkeypatch, tmp_path: Path) -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    plugin.config.layers.catalog_file = str(tmp_path / "missing.toml")
    emoji_manager_module = types.ModuleType("src.emoji_system.emoji_manager")
    emoji_manager_module.emoji_manager = types.SimpleNamespace(emojis=[DummyEmoji("preferred", "开心")])
    monkeypatch.setitem(sys.modules, "src.emoji_system.emoji_manager", emoji_manager_module)

    result = asyncio.run(
        plugin.handle_emoji_after_select(
            stream_id="stream-1",
            requested_emotion="开心",
            selected_emoji_hash="other",
            matched_emotion="开心",
        )
    )

    assert result == {"action": "continue"}


def test_layer_commands_list_set_and_clear() -> None:
    module = _load_plugin_module()
    plugin = _build_plugin(module)
    updates: list[dict[str, object]] = []

    async def fake_call_capability(capability, **kwargs):
        updates.append({"capability": capability, **kwargs})
        return {"success": True}

    plugin.ctx.call_capability = fake_call_capability
    plugin._catalog = module.EmojiLayerCatalog(
        layers={
            "q_xiang": module.EmojiLayer("q_xiang", "Q版小祥"),
            "original_xiang": module.EmojiLayer("original_xiang", "原图小祥"),
        },
        emoji_layers={},
    )
    plugin.reload_catalog = lambda: plugin._catalog

    set_result = asyncio.run(
        plugin.handle_emoji_layer_command(
            stream_id="stream-1",
            matched_groups={"layer_command": "set", "layer_args": "q_xiang original_xiang"},
        )
    )
    list_result = asyncio.run(
        plugin.handle_emoji_layer_command(
            stream_id="stream-1",
            matched_groups={"layer_command": "list", "layer_args": ""},
        )
    )
    clear_result = asyncio.run(
        plugin.handle_emoji_layer_command(
            stream_id="stream-1",
            matched_groups={"layer_command": "clear", "layer_args": ""},
        )
    )

    assert set_result[0] is True
    assert list_result[0] is True
    assert clear_result[0] is True
    assert plugin.config.layers.session_layer_overrides == {}
    assert updates[0]["capability"] == "component.update_plugin_config"
    assert "q_xiang" in plugin.ctx.send.messages[1][1]
