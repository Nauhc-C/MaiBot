from __future__ import annotations

from pathlib import Path
import importlib.util
import sys
import types


PLUGIN_DIR = Path(__file__).resolve().parents[2] / "plugins" / "skill_broker_plugin"
CORE_PATH = PLUGIN_DIR / "skill_broker_core.py"
PLUGIN_PATH = PLUGIN_DIR / "plugin.py"


def _load_core_module():
    spec = importlib.util.spec_from_file_location("skill_broker_core_test_module", CORE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_plugin_module():
    package_name = "skill_broker_plugin_test_package"
    package = types.ModuleType(package_name)
    package.__path__ = [str(PLUGIN_DIR)]
    sys.modules[package_name] = package

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
            self.config = None

        def get_components(self):
            components = []
            for attr_name in dir(self):
                attr = getattr(self, attr_name)
                info = getattr(attr, "_fake_component_info", None)
                if info is None:
                    continue
                components.append(
                    {
                        "name": info["name"],
                        "type": "TOOL",
                        "metadata": {
                            "description": info["description"],
                            "brief_description": info["description"],
                            "detailed_description": info["description"],
                            "parameters": info["parameters"],
                            "handler_name": attr_name,
                        },
                    }
                )
            return components

    def fake_tool(name, description="", parameters=None, **metadata):
        del metadata

        def decorator(func):
            func._fake_component_info = {
                "name": name,
                "description": description,
                "parameters": parameters or [],
            }
            return func

        return decorator

    class FakeToolParamType:
        STRING = "string"
        INTEGER = "integer"
        BOOLEAN = "boolean"

    class FakeToolParameterInfo:
        def __init__(self, name, param_type, description, required=False):
            self.name = name
            self.param_type = param_type
            self.description = description
            self.required = required

    fake_sdk.Field = fake_field
    fake_sdk.MaiBotPlugin = FakeMaiBotPlugin
    fake_sdk.PluginConfigBase = FakePluginConfigBase
    fake_sdk.Tool = fake_tool
    fake_sdk_types.ToolParamType = FakeToolParamType
    fake_sdk_types.ToolParameterInfo = FakeToolParameterInfo
    sys.modules["maibot_sdk"] = fake_sdk
    sys.modules["maibot_sdk.types"] = fake_sdk_types

    spec = importlib.util.spec_from_file_location(f"{package_name}.plugin", PLUGIN_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_skill(root: Path, name: str, content: str) -> Path:
    skill_dir = root / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir


def test_catalog_search_and_load_single_file_skill(tmp_path: Path) -> None:
    module = _load_core_module()
    _write_skill(
        tmp_path,
        "caveman",
        """---
name: caveman
description: >
  Ultra-compressed communication mode. Use when user wants brief mode.
---

# Caveman

Respond terse like smart caveman.
""",
    )
    broker = module.SkillBroker([str(tmp_path)])

    catalog = broker.catalog()
    search = broker.search("brief mode")
    loaded = broker.load("caveman")

    assert catalog["success"] is True
    assert "caveman" in catalog["content"]
    assert search["matched_skills"][0]["name"] == "caveman"
    assert loaded["skill_name"] == "caveman"
    assert "Respond terse" in loaded["body"]


def test_plugin_exposes_catalog_in_search_description_without_catalog_tool(tmp_path: Path) -> None:
    module = _load_plugin_module()
    _write_skill(
        tmp_path,
        "sakiko-helper",
        """---
name: sakiko-helper
description: Project scoped Sakiko helper skill.
---

# Sakiko Helper
""",
    )
    plugin = module.SkillBrokerPlugin()
    plugin.config = module.SkillBrokerPluginConfig()
    plugin.config.broker.skill_roots = [str(tmp_path)]
    plugin.config.broker.max_catalog_skills_in_description = 30

    components = plugin.get_components()
    component_names = {component["name"] for component in components}
    search_component = next(component for component in components if component["name"] == "skill_search")

    assert "skill_catalog" not in component_names
    assert "sakiko-helper" in search_component["metadata"]["description"]
    assert "Project skill catalog contains 1 local skills" in search_component["metadata"]["description"]


def test_plugin_exposes_narrow_mama_reply_roll_tool(tmp_path: Path) -> None:
    module = _load_plugin_module()
    _write_skill(
        tmp_path,
        "mama-reply",
        """---
name: mama-reply
description: Affectionate mama reply skill.
---

# Mama Reply

Call mama_reply_roll when triggered.
""",
    )
    plugin = module.SkillBrokerPlugin()
    plugin.config = module.SkillBrokerPluginConfig()
    plugin.config.broker.skill_roots = [str(tmp_path)]

    components = plugin.get_components()
    roll_component = next(component for component in components if component["name"] == "mama_reply_roll")

    assert len(roll_component["metadata"]["parameters"]) == 1
    assert roll_component["metadata"]["parameters"][0].name == "user_message"
    assert "重新掷骰" in roll_component["metadata"]["description"]
    assert "直接称作" in roll_component["metadata"]["description"]


def test_default_roots_are_project_scoped() -> None:
    module = _load_core_module()

    default_roots = [str(root) for root in module.DEFAULT_SKILL_ROOTS]

    assert default_roots
    assert all("Users" not in root for root in default_roots)
    assert all("Sakiko" in root for root in default_roots)


def test_mama_reply_roll_runs_only_fixed_skill_script(tmp_path: Path) -> None:
    module = _load_core_module()
    skill_dir = _write_skill(
        tmp_path,
        "mama-reply",
        """---
name: mama-reply
description: Affectionate mama reply skill.
---

# Mama Reply

Call mama_reply_roll when triggered.
""",
    )
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "roll_1_100.py").write_text("print('直接回复“宝宝”，不要加解释。')", encoding="utf-8")
    broker = module.SkillBroker([str(tmp_path)])

    result = broker.mama_reply_roll(user_message="小祥妈妈")

    assert result["success"] is True
    assert result["content"] == "直接回复“宝宝”，不要加解释。"
    assert result["matched_skills"][0]["name"] == "mama-reply"
    assert any("strict same-message trigger validation" in note for note in result["safety_notes"])


def test_mama_reply_roll_rejects_messages_without_strict_same_message_trigger(tmp_path: Path) -> None:
    module = _load_core_module()
    skill_dir = _write_skill(
        tmp_path,
        "mama-reply",
        """---
name: mama-reply
description: Affectionate mama reply skill.
---

# Mama Reply
""",
    )
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "roll_1_100.py").write_text("print('should not run')", encoding="utf-8")
    broker = module.SkillBroker([str(tmp_path)])

    for message in ["妈妈", "我朋友叫她妈妈", "小祥", "小祥，我朋友叫她妈妈", "上一轮小祥，这轮妈妈"]:
        result = broker.mama_reply_roll(user_message=message)

        assert result["success"] is False
        assert "trigger rejected" in result["content"]
        assert any("No roll was performed" in note for note in result["safety_notes"])


def test_load_references_reads_only_declared_local_markdown(tmp_path: Path) -> None:
    module = _load_core_module()
    skill_dir = _write_skill(
        tmp_path,
        "brainstorming",
        """---
name: brainstorming
description: Design before implementation.
---

# Brainstorming

Read [visual companion](visual-companion.md).
Read [{baseDir}/spec-document-reviewer-prompt.md]({baseDir}/spec-document-reviewer-prompt.md).
Run scripts/server.cjs only if the host supports scripts.
""",
    )
    (skill_dir / "visual-companion.md").write_text("visual details", encoding="utf-8")
    (skill_dir / "spec-document-reviewer-prompt.md").write_text("review details", encoding="utf-8")
    scripts_dir = skill_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "server.cjs").write_text("console.log('no execution');", encoding="utf-8")
    broker = module.SkillBroker([str(tmp_path)])

    loaded = broker.load("brainstorming", include_references=True)

    reference_paths = {item["relative_path"] for item in loaded["referenced_files"]}
    assert "visual-companion.md" in reference_paths
    assert "spec-document-reviewer-prompt.md" in reference_paths
    assert "script_execution" in loaded["unsupported_capabilities"]
    assert any("not executed" in note for note in loaded["safety_notes"])


def test_malformed_frontmatter_falls_back_to_directory_name(tmp_path: Path) -> None:
    module = _load_core_module()
    _write_skill(
        tmp_path,
        "broken_skill",
        """---
name: broken
description: missing close

# Broken
""",
    )
    broker = module.SkillBroker([str(tmp_path)])

    loaded = broker.load("broken_skill")

    assert loaded["success"] is True
    assert loaded["skill_name"] == "broken_skill"
    assert loaded["matched_skills"][0]["warnings"]


def test_out_of_skill_reference_is_blocked(tmp_path: Path) -> None:
    module = _load_core_module()
    _write_skill(
        tmp_path,
        "safe_skill",
        """---
name: safe-skill
description: Must not read parent files.
---

# Safe

Read [secret](../secret.md).
""",
    )
    (tmp_path / "secret.md").write_text("do not expose", encoding="utf-8")
    broker = module.SkillBroker([str(tmp_path)])

    loaded = broker.load("safe-skill", include_references=True)

    assert loaded["referenced_files"] == []
    assert "do not expose" not in loaded["content"]
    assert any("blocked out-of-skill reference" in warning for warning in loaded["matched_skills"][0]["warnings"])


def test_search_quality_for_distinct_queries(tmp_path: Path) -> None:
    module = _load_core_module()
    _write_skill(
        tmp_path,
        "openai-docs",
        """---
name: openai-docs
description: Use for OpenAI API docs, model guidance, and official documentation.
---
# OpenAI Docs
""",
    )
    _write_skill(
        tmp_path,
        "brainstorming",
        """---
name: brainstorming
description: Design and spec workflow before implementation.
---
# Brainstorming
""",
    )
    _write_skill(
        tmp_path,
        "caveman",
        """---
name: caveman
description: Brief compressed communication mode.
---
# Caveman
""",
    )
    broker = module.SkillBroker([str(tmp_path)])

    assert broker.search("OpenAI API docs")["matched_skills"][0]["name"] == "openai-docs"
    assert broker.search("brainstorming design")["matched_skills"][0]["name"] == "brainstorming"
    assert broker.search("brief mode")["matched_skills"][0]["name"] == "caveman"
