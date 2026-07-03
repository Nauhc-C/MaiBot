"""关键词上下文注入插件。

在 Maisaka planner/replyer 即将请求模型时，扫描最近几条真实用户消息；
命中配置规则后，追加一条极短 user 上下文消息。
"""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import logging
import re
from typing import Any, List, Sequence

from maibot_sdk import Field, HookHandler, MaiBotPlugin, PluginConfigBase, Tool
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder, ToolParameterInfo, ToolParamType

logger = logging.getLogger("context_injector_plugin")

_PLUGIN_ID = "maibot-team.context-injector"
_INJECTION_HEADER = "【当前对话背景】"
_MAX_RECENT_USER_MESSAGE_LIMIT = 64
_MAX_SEARCH_CONTEXT_LIMIT = 20


def _tool_param(name: str, param_type: ToolParamType, description: str, required: bool) -> ToolParameterInfo:
    return ToolParameterInfo(name=name, param_type=param_type, description=description, required=required)


class PluginSectionConfig(PluginConfigBase):
    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(default=True, description="是否启用关键词上下文注入插件")
    config_version: str = Field(default="1.0.0", description="配置版本")


class MatchingConfig(PluginConfigBase):
    __ui_label__ = "匹配"
    __ui_icon__ = "search"
    __ui_order__ = 1

    recent_user_message_limit: int = Field(default=8, description="扫描最近多少条真实用户消息")


class ContextInjectionRule(PluginConfigBase):
    """一条关键词到背景事实的注入规则。"""

    enabled: bool = Field(default=False, description="是否启用此规则")
    name: str = Field(default="初华当前处境", description="规则名称，用于日志和去重")
    keywords: List[str] = Field(default_factory=lambda: ["初华", "三角初华"], description="任意命中即触发的关键词")
    context: str = Field(default="三角初华现在正在和祥子住在一起，祥子睡阁楼。", description="注入的背景事实")
    inject_to_planner: bool = Field(default=True, description="是否注入 planner 请求")
    inject_to_replyer: bool = Field(default=True, description="是否注入 replyer 模型请求")


class ContextInjectorPluginConfig(PluginConfigBase):
    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    matching: MatchingConfig = Field(default_factory=MatchingConfig)
    rules: List[ContextInjectionRule] = Field(
        default_factory=lambda: [ContextInjectionRule()],
        description="关键词上下文注入规则列表",
    )


@dataclass(frozen=True)
class RuleHit:
    key: str
    rule: ContextInjectionRule


class ContextInjectorPlugin(MaiBotPlugin):
    """按关键词向 planner/replyer 注入短背景事实。"""

    config_model = ContextInjectorPluginConfig

    _METADATA_USER_MESSAGE_PATTERNS: Sequence[re.Pattern[str]] = (
        re.compile(r"^当前时间：\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\s*$"),
        re.compile(r"^【人物画像-内部参考】"),
        re.compile(r"^<system-reminder>"),
        re.compile(r"^当前聊天额外注意事项："),
        re.compile(r"^【角色资料兜底-内部参考】"),
        re.compile(r"^【可选上下文\s*-\s*Bot 的当前日程】"),
        re.compile(r"^【角色当前状态】"),
        re.compile(rf"^{re.escape(_INJECTION_HEADER)}"),
    )
    _PLANNER_PREFIX_PATTERN: re.Pattern[str] = re.compile(r"^<message\s+[^>]*>\s*\n?")

    def __init__(self) -> None:
        super().__init__()
        self._active_rule_keys_by_session: dict[str, set[str]] = {}
        self._injected_stage_by_session_rule: dict[tuple[str, str], str] = {}
        self._delivered_rule_keys_by_session: dict[str, set[str]] = {}

    async def on_load(self) -> None:
        logger.info("[%s] 插件已加载", _PLUGIN_ID)

    async def on_unload(self) -> None:
        logger.info("[%s] 插件已卸载", _PLUGIN_ID)

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        del config_data
        self._active_rule_keys_by_session.clear()
        self._injected_stage_by_session_rule.clear()
        self._delivered_rule_keys_by_session.clear()
        logger.info("[%s] 配置已更新，已清空话题去重状态: scope=%s version=%s", _PLUGIN_ID, scope, version)

    @staticmethod
    def _strip_planner_prefix(text: str) -> str:
        return ContextInjectorPlugin._PLANNER_PREFIX_PATTERN.sub("", str(text or ""), count=1)

    @classmethod
    def _is_metadata_user_text(cls, text: str) -> bool:
        normalized = cls._strip_planner_prefix(text).strip()
        if not normalized:
            return True
        return any(pattern.match(normalized) for pattern in cls._METADATA_USER_MESSAGE_PATTERNS)

    @classmethod
    def _extract_text_from_content(cls, content: Any) -> str:
        if isinstance(content, str):
            return cls._strip_planner_prefix(content).strip()

        if not isinstance(content, list):
            return ""

        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                candidate = item
            elif isinstance(item, dict):
                candidate = ""
                if "text" in item:
                    candidate = str(item.get("text") or item.get("content") or "")
                elif str(item.get("type") or "").strip().lower() == "text":
                    candidate = str(item.get("content") or "")
            else:
                candidate = ""

            normalized = cls._strip_planner_prefix(candidate).strip()
            if normalized:
                parts.append(normalized)

        return "\n".join(parts).strip()

    @classmethod
    def _extract_recent_real_user_texts(cls, messages: Any, limit: int) -> list[str]:
        if not isinstance(messages, list) or limit <= 0:
            return []

        recent_texts: list[str] = []
        for message in reversed(messages):
            if not isinstance(message, dict):
                continue
            if str(message.get("role") or "").strip().lower() != "user":
                continue

            text = cls._extract_text_from_content(message.get("content"))
            if not text or cls._is_metadata_user_text(text):
                continue

            recent_texts.append(text)
            if len(recent_texts) >= limit:
                break

        recent_texts.reverse()
        return recent_texts

    def _get_recent_user_message_limit(self) -> int:
        try:
            raw_limit = getattr(getattr(self.config, "matching", None), "recent_user_message_limit", 8)
            parsed_limit = int(raw_limit)
        except (TypeError, ValueError):
            parsed_limit = 8
        return max(1, min(parsed_limit, _MAX_RECENT_USER_MESSAGE_LIMIT))

    def _is_plugin_enabled(self) -> bool:
        try:
            return bool(getattr(getattr(self.config, "plugin", None), "enabled", False))
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _normalize_keywords(raw_keywords: Any) -> list[str]:
        if isinstance(raw_keywords, str):
            candidates = [raw_keywords]
        elif isinstance(raw_keywords, list):
            candidates = [str(item or "") for item in raw_keywords]
        else:
            candidates = []
        return [keyword.strip() for keyword in candidates if keyword.strip()]

    @staticmethod
    def _normalize_search_text(text: Any) -> str:
        return re.sub(r"\s+", "", str(text or "")).lower()

    def _iter_enabled_rules(self) -> list[tuple[str, ContextInjectionRule]]:
        raw_rules = getattr(self.config, "rules", [])
        if not isinstance(raw_rules, list):
            return []

        enabled_rules: list[tuple[str, ContextInjectionRule]] = []
        seen_keys: set[str] = set()
        for index, rule in enumerate(raw_rules, start=1):
            if not bool(getattr(rule, "enabled", False)):
                continue
            if not self._normalize_keywords(getattr(rule, "keywords", [])):
                continue
            if not str(getattr(rule, "context", "") or "").strip():
                continue

            rule_name = str(getattr(rule, "name", "") or "").strip() or f"rule_{index}"
            if rule_name in seen_keys:
                continue
            seen_keys.add(rule_name)
            enabled_rules.append((rule_name, rule))
        return enabled_rules

    @staticmethod
    def _rule_payload(rule_key: str, rule: ContextInjectionRule, *, score: float | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": str(getattr(rule, "name", "") or rule_key).strip() or rule_key,
            "keywords": ContextInjectorPlugin._normalize_keywords(getattr(rule, "keywords", [])),
            "context": str(getattr(rule, "context", "") or "").strip(),
        }
        if score is not None:
            payload["score"] = round(float(score), 4)
        return payload

    def _mark_rules_delivered(self, session_id: str, rule_keys: Sequence[str]) -> None:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return
        delivered_keys = self._delivered_rule_keys_by_session.setdefault(normalized_session_id, set())
        delivered_keys.update(str(rule_key) for rule_key in rule_keys if str(rule_key or "").strip())

    def _is_rule_delivered(self, session_id: str, rule_key: str) -> bool:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id:
            return False
        return str(rule_key or "").strip() in self._delivered_rule_keys_by_session.get(normalized_session_id, set())

    def _score_rule_for_query(self, query: str, rule_key: str, rule: ContextInjectionRule) -> float:
        normalized_query = self._normalize_search_text(query)
        if not normalized_query:
            return 0.0

        name = str(getattr(rule, "name", "") or rule_key).strip()
        keywords = self._normalize_keywords(getattr(rule, "keywords", []))
        context = str(getattr(rule, "context", "") or "").strip()

        normalized_name = self._normalize_search_text(name)
        normalized_context = self._normalize_search_text(context)
        normalized_keywords = [self._normalize_search_text(keyword) for keyword in keywords]

        score = 0.0
        if normalized_query == normalized_name:
            score = max(score, 120.0)
        if normalized_query and normalized_query in normalized_name:
            score = max(score, 100.0 + min(len(normalized_query), 20))
        for keyword, normalized_keyword in zip(keywords, normalized_keywords, strict=False):
            if not normalized_keyword:
                continue
            if normalized_query == normalized_keyword:
                score = max(score, 115.0)
            elif normalized_query in normalized_keyword or normalized_keyword in normalized_query:
                score = max(score, 90.0 + min(len(normalized_keyword), len(normalized_query), 20))
            elif normalized_query in self._normalize_search_text(keyword):
                score = max(score, 70.0)
        if normalized_query in normalized_context:
            score = max(score, 65.0 + min(len(normalized_query), 20))

        haystacks = [normalized_name, normalized_context, *normalized_keywords]
        fuzzy_score = max(
            (SequenceMatcher(None, normalized_query, haystack[: max(len(normalized_query) * 3, 24)]).ratio() for haystack in haystacks if haystack),
            default=0.0,
        )
        return max(score, fuzzy_score * 60.0)

    def _search_context_rules(
        self,
        *,
        query: str,
        limit: int,
        session_id: str = "",
        include_injected: bool = False,
    ) -> list[tuple[str, ContextInjectionRule, float]]:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return []

        safe_limit = max(1, min(int(limit or 5), _MAX_SEARCH_CONTEXT_LIMIT))
        scored_rules: list[tuple[str, ContextInjectionRule, float]] = []
        for rule_key, rule in self._iter_enabled_rules():
            if not include_injected and self._is_rule_delivered(session_id, rule_key):
                continue
            score = self._score_rule_for_query(normalized_query, rule_key, rule)
            if score <= 0:
                continue
            scored_rules.append((rule_key, rule, score))

        scored_rules.sort(key=lambda item: (-item[2], item[0]))
        return scored_rules[:safe_limit]

    def _match_rules(self, recent_user_texts: Sequence[str]) -> list[RuleHit]:
        if not recent_user_texts:
            return []

        combined_text = "\n".join(str(text or "") for text in recent_user_texts)
        hits: list[RuleHit] = []
        for rule_key, rule in self._iter_enabled_rules():
            keywords = self._normalize_keywords(getattr(rule, "keywords", []))
            if any(keyword in combined_text for keyword in keywords):
                hits.append(RuleHit(key=rule_key, rule=rule))
        return hits

    @staticmethod
    def _rule_targets_stage(rule: ContextInjectionRule, stage: str) -> bool:
        if stage == "planner":
            return bool(getattr(rule, "inject_to_planner", True))
        if stage == "replyer":
            return bool(getattr(rule, "inject_to_replyer", True))
        return False

    def _select_rules_to_inject(self, session_id: str, matched_hits: Sequence[RuleHit], stage: str) -> list[RuleHit]:
        matched_keys = {hit.key for hit in matched_hits}
        active_keys = self._active_rule_keys_by_session.setdefault(session_id, set())

        expired_keys = active_keys - matched_keys
        for expired_key in expired_keys:
            self._injected_stage_by_session_rule.pop((session_id, expired_key), None)
        if expired_keys:
            active_keys.difference_update(expired_keys)

        selected_hits: list[RuleHit] = []
        for hit in matched_hits:
            active_keys.add(hit.key)
            injected_state_key = (session_id, hit.key)
            if injected_state_key in self._injected_stage_by_session_rule:
                continue
            if not self._rule_targets_stage(hit.rule, stage):
                continue
            self._injected_stage_by_session_rule[injected_state_key] = stage
            selected_hits.append(hit)

        self._mark_rules_delivered(session_id, [hit.key for hit in selected_hits])
        return selected_hits

    @staticmethod
    def _build_injection_text(hits: Sequence[RuleHit]) -> str:
        lines = [
            _INJECTION_HEADER,
            "这段事实可作为角色已知背景使用，不要主动说明信息来源。",
        ]
        for hit in hits:
            rule_name = str(getattr(hit.rule, "name", "") or hit.key).strip() or hit.key
            context = str(getattr(hit.rule, "context", "") or "").strip()
            if context:
                lines.append(f"- {rule_name}：{context}")
        return "\n".join(lines).strip()

    @staticmethod
    def _append_user_message(messages: list[dict[str, Any]], injection_text: str) -> list[dict[str, Any]]:
        modified_messages = list(messages)
        modified_messages.append({"role": "user", "content": injection_text})
        return modified_messages

    @staticmethod
    def _preview(text: str, max_length: int = 80) -> str:
        normalized = " ".join(str(text or "").split())
        if len(normalized) <= max_length:
            return normalized
        return f"{normalized[:max_length]}...<len={len(normalized)}>"

    def _prepare_injection_text(self, messages: Any, session_id: str, stage: str) -> str:
        normalized_session_id = str(session_id or "").strip()
        if not normalized_session_id or not self._is_plugin_enabled():
            return ""

        limit = self._get_recent_user_message_limit()
        recent_user_texts = self._extract_recent_real_user_texts(messages, limit)
        matched_hits = self._match_rules(recent_user_texts)
        selected_hits = self._select_rules_to_inject(normalized_session_id, matched_hits, stage)
        if not selected_hits:
            return ""

        injection_text = self._build_injection_text(selected_hits)
        rule_names = [str(getattr(hit.rule, "name", "") or hit.key).strip() or hit.key for hit in selected_hits]
        logger.info(
            "[%s] 命中关键词上下文规则: session=%s stage=%s rules=%s preview=%s",
            _PLUGIN_ID,
            normalized_session_id,
            stage,
            ",".join(rule_names),
            self._preview(injection_text),
        )
        return injection_text

    def _handle_stage(self, *, messages: Any, session_id: str, stage: str) -> dict[str, Any]:
        if not isinstance(messages, list) or not messages:
            return {"action": "continue"}

        injection_text = self._prepare_injection_text(messages, session_id, stage)
        if not injection_text:
            return {"action": "continue"}

        return {
            "action": "continue",
            "modified_kwargs": {
                "messages": self._append_user_message(messages, injection_text),
            },
        }

    @HookHandler(
        "maisaka.planner.before_request",
        name="inject_context_before_planner",
        description="在 planner 请求前按关键词注入预设背景事实。",
        mode=HookMode.BLOCKING,
        order=HookOrder.NORMAL,
        error_policy=ErrorPolicy.SKIP,
    )
    async def inject_context_before_planner(
        self,
        messages: Any = None,
        session_id: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        try:
            return self._handle_stage(messages=messages, session_id=session_id, stage="planner")
        except Exception:  # noqa: BLE001
            logger.exception("[%s] planner 上下文注入失败: session=%s", _PLUGIN_ID, session_id)
            return {"action": "continue"}

    @HookHandler(
        "maisaka.replyer.before_model_request",
        name="inject_context_before_replyer_model",
        description="在 replyer 模型请求前按关键词注入预设背景事实。",
        mode=HookMode.BLOCKING,
        order=HookOrder.NORMAL,
        error_policy=ErrorPolicy.SKIP,
    )
    async def inject_context_before_replyer_model(
        self,
        messages: Any = None,
        session_id: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        del kwargs
        try:
            return self._handle_stage(messages=messages, session_id=session_id, stage="replyer")
        except Exception:  # noqa: BLE001
            logger.exception("[%s] replyer 上下文注入失败: session=%s", _PLUGIN_ID, session_id)
            return {"action": "continue"}

    @Tool(
        "search_context_rules",
        description=(
            "按自然语言模糊搜索关键词上下文注入规则。"
            "用于主动查找角色关系、背景事实、时间线和固定设定；默认不会返回本会话已注入或已返回过的规则。"
        ),
        parameters=[
            _tool_param("query", ToolParamType.STRING, "搜索词，例如 祥子父亲、初华身世、睦和祥子关系", True),
            _tool_param("limit", ToolParamType.INTEGER, "最多返回多少条；默认 5，最大 20", False),
            _tool_param("include_injected", ToolParamType.BOOLEAN, "是否允许返回本会话已注入或已返回过的规则；默认 false", False),
        ],
        visibility="visible",
    )
    async def handle_search_context_rules(
        self,
        query: str = "",
        limit: int | None = None,
        include_injected: bool = False,
        stream_id: str = "",
        chat_id: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        session_id = str(stream_id or chat_id or kwargs.get("session_id") or "").strip()
        if not self._is_plugin_enabled():
            return {
                "success": False,
                "content": "关键词上下文注入器未启用。",
                "results": [],
            }

        safe_limit = max(1, min(int(limit or 5), _MAX_SEARCH_CONTEXT_LIMIT))
        matches = self._search_context_rules(
            query=query,
            limit=safe_limit,
            session_id=session_id,
            include_injected=bool(include_injected),
        )
        result_rule_keys = [rule_key for rule_key, _, _ in matches]
        if not include_injected:
            self._mark_rules_delivered(session_id, result_rule_keys)

        results = [
            self._rule_payload(rule_key, rule, score=score)
            for rule_key, rule, score in matches
        ]
        content = "未找到可用的上下文规则。" if not results else self._build_search_tool_content(results)
        logger.info(
            "[%s] 主动搜索上下文规则: session=%s query=%s results=%s include_injected=%s",
            _PLUGIN_ID,
            session_id or "<none>",
            self._preview(query, 40),
            ",".join(result["name"] for result in results),
            bool(include_injected),
        )
        return {
            "success": True,
            "content": content,
            "results": results,
            "filtered_already_delivered": not bool(include_injected),
        }

    @staticmethod
    def _build_search_tool_content(results: Sequence[dict[str, Any]]) -> str:
        lines = ["【可用上下文规则】"]
        for result in results:
            name = str(result.get("name") or "").strip()
            context = str(result.get("context") or "").strip()
            if name and context:
                lines.append(f"- {name}：{context}")
        return "\n".join(lines).strip()


def create_plugin() -> ContextInjectorPlugin:
    return ContextInjectorPlugin()
