"""Skill Broker plugin for reading standard local ``SKILL.md`` bundles."""

from __future__ import annotations

from typing import Any

from maibot_sdk import Field, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

from .skill_broker_core import DEFAULT_SKILL_ROOTS, SkillBroker


def _tool_param(name: str, param_type: ToolParamType, description: str, required: bool) -> ToolParameterInfo:
    return ToolParameterInfo(name=name, param_type=param_type, description=description, required=required)


class PluginSectionConfig(PluginConfigBase):
    """Plugin-level settings."""

    __ui_label__ = "插件"
    __ui_icon__ = "library"
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用 Skill Broker")
    config_version: str = Field(default="1.0.0", description="配置版本")


class SkillBrokerConfig(PluginConfigBase):
    """Skill scanning and loading settings."""

    __ui_label__ = "Skill Broker"
    __ui_icon__ = "search"
    __ui_order__ = 1

    skill_roots: list[str] = Field(default_factory=lambda: list(DEFAULT_SKILL_ROOTS), description="要扫描的 skill 根目录")
    max_search_results: int = Field(default=5, description="skill_search 默认最多返回多少条")
    max_catalog_skills_in_description: int = Field(default=30, description="工具描述里最多常驻多少条 skill 索引")
    max_body_chars: int = Field(default=20000, description="单个 SKILL.md 或引用文件最多返回多少字符")
    allow_reference_files: bool = Field(default=True, description="是否允许读取 skill 同目录内明确引用的 Markdown 文件")
    allow_script_execution: bool = Field(default=False, description="是否允许执行 skill scripts；v1 默认关闭且插件不会执行脚本")


class SkillBrokerPluginConfig(PluginConfigBase):
    """Top-level plugin config."""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    broker: SkillBrokerConfig = Field(default_factory=SkillBrokerConfig)


class SkillBrokerPlugin(MaiBotPlugin):
    """Expose local standard skills to the planner as searchable tools."""

    config_model = SkillBrokerPluginConfig

    def __init__(self) -> None:
        super().__init__()
        self._broker: SkillBroker | None = None

    async def on_load(self) -> None:
        self._broker = self._build_broker()
        self._broker.refresh(force=True)

    async def on_unload(self) -> None:
        self._broker = None

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        del scope, config_data, version
        self._broker = self._build_broker()
        self._broker.refresh(force=True)

    def _get_config_or_default(self) -> SkillBrokerPluginConfig:
        try:
            config = self.config
        except RuntimeError:
            return SkillBrokerPluginConfig()
        return config

    def _build_broker(self) -> SkillBroker:
        broker_config = self._get_config_or_default().broker
        return SkillBroker(
            skill_roots=[str(root) for root in broker_config.skill_roots],
            max_search_results=int(broker_config.max_search_results),
            max_body_chars=int(broker_config.max_body_chars),
            allow_reference_files=bool(broker_config.allow_reference_files),
            allow_script_execution=bool(broker_config.allow_script_execution),
        )

    def _get_broker(self) -> SkillBroker:
        if self._broker is None:
            self._broker = self._build_broker()
        return self._broker

    def _disabled_result(self) -> dict[str, Any]:
        return {
            "success": False,
            "content": "Skill Broker 插件未启用。",
            "matched_skills": [],
            "safety_notes": ["Enable plugin.skill_broker_plugin.plugin.enabled before using skill tools."],
        }

    def get_components(self) -> list[dict[str, Any]]:
        """Expose skill catalog in the skill_search tool description."""

        components = super().get_components()
        config = self._get_config_or_default()
        if not config.plugin.enabled:
            return components

        catalog_text = self._get_broker().catalog_text(
            max_lines=int(config.broker.max_catalog_skills_in_description)
        )
        search_description = (
            "按自然语言查询 Sakiko 项目级标准 SKILL.md 技能。"
            "下面是当前常驻轻量索引；需要完整说明时调用 skill_load(name)。\n"
            f"{catalog_text}"
        )
        for component in components:
            if component.get("name") != "skill_search":
                continue
            metadata = component.get("metadata")
            if not isinstance(metadata, dict):
                continue
            metadata["description"] = search_description
            metadata["brief_description"] = search_description
            metadata["detailed_description"] = search_description
        return components

    @Tool(
        "skill_search",
        description="按自然语言查询 Sakiko 项目级标准 SKILL.md 技能；工具描述会常驻展示当前轻量 skill 索引。",
        parameters=[
            _tool_param("query", ToolParamType.STRING, "搜索词，例如 OpenAI docs、brainstorming design、brief mode", True),
            _tool_param("limit", ToolParamType.INTEGER, "最多返回多少条；不填则使用插件配置", False),
        ],
        visibility="visible",
    )
    async def handle_skill_search(self, query: str = "", limit: int | None = None, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        if not self._get_config_or_default().plugin.enabled:
            return self._disabled_result()
        return self._get_broker().search(query=query, limit=limit)

    @Tool(
        "skill_load",
        description="读取指定 Sakiko 项目级标准 skill 的 SKILL.md 全文；需要附属说明时可 include_references=true。",
        parameters=[
            _tool_param("name", ToolParamType.STRING, "skill 名称，例如 brainstorming、openai-docs、caveman", True),
            _tool_param("include_references", ToolParamType.BOOLEAN, "是否读取 skill 同目录内明确引用的 Markdown 文件", False),
        ],
        visibility="visible",
    )
    async def handle_skill_load(
        self,
        name: str = "",
        include_references: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        if not self._get_config_or_default().plugin.enabled:
            return self._disabled_result()
        return self._get_broker().load(name=name, include_references=include_references)

    @Tool(
        "mama_reply_roll",
        description=(
            "仅当同一条用户发言里把机器人直接称作“小祥妈妈/祥子妈咪/sakiko 妈妈”等时调用。"
            "绝对不要用于用户叫其他人妈妈/妈咪的情况。该工具每次调用都会重新掷骰，只返回本轮应注入的内部回复提示；不要向用户复述工具调用过程。"
        ),
        parameters=[
            _tool_param(
                "user_message",
                ToolParamType.STRING,
                "本轮用户原始发言；必须是同一条发言，不要拼接历史上下文。",
                True,
            )
        ],
        visibility="visible",
    )
    async def handle_mama_reply_roll(self, user_message: str = "", **kwargs: Any) -> dict[str, Any]:
        del kwargs
        if not self._get_config_or_default().plugin.enabled:
            return self._disabled_result()
        return self._get_broker().mama_reply_roll(user_message=user_message)


def create_plugin() -> SkillBrokerPlugin:
    """Create the plugin instance."""

    return SkillBrokerPlugin()
