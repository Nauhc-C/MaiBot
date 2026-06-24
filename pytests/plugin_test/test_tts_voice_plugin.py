import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "xuqian13_tts-voice-plugin"
TEST_PACKAGE_NAME = "tts_voice_plugin_testpkg"


def _ensure_package(module_name: str, package_path: Path) -> None:
    package_module = sys.modules.get(module_name)
    if package_module is None:
        package_module = types.ModuleType(module_name)
        package_module.__path__ = [str(package_path)]
        sys.modules[module_name] = package_module


def _load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载模块: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_tts_plugin_modules():
    _ensure_package(TEST_PACKAGE_NAME, PLUGIN_DIR)
    _ensure_package(f"{TEST_PACKAGE_NAME}.backends", PLUGIN_DIR / "backends")
    _ensure_package(f"{TEST_PACKAGE_NAME}.utils", PLUGIN_DIR / "utils")

    config_keys_module = _load_module(f"{TEST_PACKAGE_NAME}.config_keys", PLUGIN_DIR / "config_keys.py")
    _load_module(f"{TEST_PACKAGE_NAME}.utils.file", PLUGIN_DIR / "utils" / "file.py")
    _load_module(f"{TEST_PACKAGE_NAME}.utils.text", PLUGIN_DIR / "utils" / "text.py")
    _load_module(f"{TEST_PACKAGE_NAME}.utils.session", PLUGIN_DIR / "utils" / "session.py")
    base_module = _load_module(f"{TEST_PACKAGE_NAME}.backends.base", PLUGIN_DIR / "backends" / "base.py")
    _load_module(f"{TEST_PACKAGE_NAME}.backends.ai_voice", PLUGIN_DIR / "backends" / "ai_voice.py")
    _load_module(f"{TEST_PACKAGE_NAME}.backends.gsv2p", PLUGIN_DIR / "backends" / "gsv2p.py")
    _load_module(f"{TEST_PACKAGE_NAME}.backends.gpt_sovits", PLUGIN_DIR / "backends" / "gpt_sovits.py")
    _load_module(f"{TEST_PACKAGE_NAME}.backends.doubao", PLUGIN_DIR / "backends" / "doubao.py")
    _load_module(f"{TEST_PACKAGE_NAME}.backends.cosyvoice", PLUGIN_DIR / "backends" / "cosyvoice.py")
    _load_module(f"{TEST_PACKAGE_NAME}.backends.mimo", PLUGIN_DIR / "backends" / "mimo.py")
    _load_module(f"{TEST_PACKAGE_NAME}.backends.minimax", PLUGIN_DIR / "backends" / "minimax.py")
    _load_module(f"{TEST_PACKAGE_NAME}.backends", PLUGIN_DIR / "backends" / "__init__.py")
    plugin_module = _load_module(f"{TEST_PACKAGE_NAME}.plugin", PLUGIN_DIR / "plugin.py")
    return config_keys_module, base_module, plugin_module


@pytest.fixture(scope="module")
def tts_modules():
    return _load_tts_plugin_modules()


@pytest.mark.asyncio
async def test_send_audio_returns_failure_when_send_custom_rejects(tts_modules):
    config_keys_module, base_module, _plugin_module = tts_modules
    config_keys = config_keys_module.ConfigKeys
    backend_base = base_module.TTSBackendBase

    class DummyBackend(backend_base):
        backend_name = "dummy"

        async def execute(self, text: str, voice: str | None = None, **kwargs):
            raise NotImplementedError

    backend = DummyBackend(
        config_getter=lambda key, default=None: True if key == config_keys.GENERAL_USE_BASE64_AUDIO else default,
        log_prefix="[test]",
    )

    async def _reject_send(**kwargs):
        return False

    backend.set_send_custom(_reject_send)
    result = await backend.send_audio(b"RIFF" + (b"\x00" * 256), audio_format="wav")

    assert result.success is False
    assert result.message == "发送语音消息失败"


@pytest.mark.asyncio
async def test_execute_backend_falls_back_to_available_default(tts_modules, monkeypatch):
    _config_keys_module, _base_module, plugin_module = tts_modules
    unified_plugin_class = plugin_module.UnifiedTTSPlugin
    tts_result_class = plugin_module.TTSResult

    plugin = object.__new__(unified_plugin_class)
    plugin._plugin_config_instance = SimpleNamespace(general=SimpleNamespace(default_backend="gpt_sovits"))
    plugin._ctx = SimpleNamespace(logger=SimpleNamespace(warning=lambda *args, **kwargs: None))

    class FakeBackend:
        def __init__(self, *, valid: bool, error_message: str = "", result_message: str = ""):
            self._valid = valid
            self._error_message = error_message
            self._result_message = result_message or "ok"

        def validate_config(self):
            return self._valid, self._error_message

        async def execute(self, text, voice, emotion=""):
            return tts_result_class(True, f"{self._result_message}:{text}:{voice}:{emotion}", backend_name="fake")

    backend_map = {
        "doubao": FakeBackend(valid=False, error_message="豆包未配置"),
        "gpt_sovits": FakeBackend(valid=True, result_message="fallback"),
    }

    monkeypatch.setattr(plugin, "_get_default_backend", lambda: "gpt_sovits")
    monkeypatch.setattr(plugin, "_pick_ai_voice_fallback", lambda log_prefix, is_private=False: "gpt_sovits")
    monkeypatch.setattr(plugin, "_create_backend", lambda backend_name, stream_id, log_prefix: backend_map.get(backend_name))

    result = await plugin._execute_backend(
        "doubao",
        "你好",
        "stream-1",
        "[test]",
        voice="voice-style",
        emotion="happy",
        allow_backend_fallback=True,
    )

    assert result.success is True
    assert result.message == "fallback:你好:voice-style:happy"


def test_tts_action_is_visible_to_planner(tts_modules):
    _config_keys_module, _base_module, plugin_module = tts_modules
    component_info = getattr(plugin_module.UnifiedTTSPlugin.handle_tts_action, "__maibot_component_info__")

    assert component_info.metadata["legacy_action"] is True
    assert component_info.metadata["visibility"] == "visible"
