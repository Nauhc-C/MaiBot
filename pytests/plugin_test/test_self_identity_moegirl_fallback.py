from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
import types


PLUGIN_PATH = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "sengokucola_self-identity-plugin"
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

        def get_components(self):
            return []

    def fake_tool(*args, **kwargs):
        def decorator(func):
            return func

        return decorator

    class FakeToolParameterInfo:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeToolParamType:
        STRING = "string"
        INTEGER = "integer"

    fake_sdk.Field = fake_field
    fake_sdk.MaiBotPlugin = FakeMaiBotPlugin
    fake_sdk.PluginConfigBase = FakePluginConfigBase
    fake_sdk.Tool = fake_tool
    fake_sdk_types.ToolParameterInfo = FakeToolParameterInfo
    fake_sdk_types.ToolParamType = FakeToolParamType

    sys.modules["maibot_sdk"] = fake_sdk
    sys.modules["maibot_sdk.types"] = fake_sdk_types

    spec = importlib.util.spec_from_file_location("self_identity_plugin_test_module", PLUGIN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extract_moegirl_info_rows_reads_basic_fields() -> None:
    module = _load_plugin_module()
    html = """
    <html>
      <head><title>祐天寺若麦 - 萌娘百科 万物皆可萌的百科全书</title></head>
      <body>
        <table class="infoboxSpecial">
          <tr><th>髮色</th><td><a>紫髪</a></td></tr>
          <tr><th>瞳色</th><td><a>粉瞳</a></td></tr>
          <tr><th>身高</th><td>164cm</td></tr>
          <tr><th>萌点</th><td><a>美少女</a>、<a>短发</a>、<a>猫嘴</a></td></tr>
        </table>
      </body>
    </html>
    """

    fields = module._extract_moegirl_info_rows(html)

    assert fields["发色"] == "紫髪"
    assert fields["瞳色"] == "粉瞳"
    assert fields["身高"] == "164cm"
    assert fields["萌点"] == "美少女、短发、猫嘴"


def test_planner_before_request_injects_reference_for_appearance_query() -> None:
    module = _load_plugin_module()
    plugin = module.SelfIdentityPlugin()
    target_url = "https://zh.moegirl.org.cn/%E7%A5%90%E5%A4%A9%E5%AF%BA%E8%8B%A5%E9%BA%A6"

    plugin._moegirl_page_cache[target_url] = {
        "title": "祐天寺若麦",
        "url": target_url,
        "fields": {
            "发色": "紫髪",
            "瞳色": "粉瞳",
            "身高": "164cm",
            "萌点": "美少女、短发、猫嘴",
        },
    }

    messages = [
        {"role": "assistant", "content": f"词条:祐天寺若麦\n链接:{target_url}"},
        {"role": "user", "content": "喵梦长什么样"},
    ]

    result = asyncio.run(plugin.handle_planner_before_request(messages=messages))

    assert result["action"] == "continue"
    modified_messages = result["modified_kwargs"]["messages"]
    assert len(modified_messages) == 3
    injected_message = modified_messages[-1]
    assert injected_message["role"] == "user"
    assert "角色资料兜底-内部参考" in injected_message["content"]
    assert "发色：紫髪" in injected_message["content"]
    assert "瞳色：粉瞳" in injected_message["content"]
    assert "萌点：美少女、短发、猫嘴" in injected_message["content"]
