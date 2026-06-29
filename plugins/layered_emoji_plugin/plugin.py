"""Layered emoji selection plugin.

This plugin sits outside the built-in emoji sender. It listens to the
``emoji.maisaka.after_select`` hook and, when possible, replaces the selected
emoji with another registered emoji from the configured layer pool.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
import math
import random
import re
import shlex
import tomllib
from typing import Any, ClassVar

from maibot_sdk import Command, Field, HookHandler, MaiBotPlugin, PluginConfigBase
from maibot_sdk.types import ErrorPolicy, HookMode, HookOrder


_PLUGIN_ID = "openai-codex.layered-emoji-plugin"
_DEFAULT_CATALOG_FILE = "emoji_layers.toml"
_UNCLASSIFIED_LAYER_ID = "unclassified"
_EMOTION_SPLIT_RE = re.compile(r"[,，、;；\r\n\t]+")


@dataclass(frozen=True)
class EmojiLayer:
    """One selectable emoji layer."""

    layer_id: str
    name: str
    weight: float = 1.0
    enabled_by_default: bool = True


@dataclass
class EmojiLayerCatalog:
    """Parsed emoji layer manifest."""

    layers: dict[str, EmojiLayer] = field(default_factory=dict)
    emoji_layers: dict[str, set[str]] = field(default_factory=dict)

    def get_layers_for_hash(self, emoji_hash: str) -> set[str]:
        normalized_hash = normalize_hash(emoji_hash)
        if not normalized_hash:
            return set()
        return set(self.emoji_layers.get(normalized_hash, set()))

    @property
    def selectable_layer_ids(self) -> set[str]:
        return set(self.layers)


class PluginSectionConfig(PluginConfigBase):
    """Plugin-level settings."""

    __ui_label__: ClassVar[str] = "插件"
    __ui_icon__: ClassVar[str] = "layers"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(default=True, description="是否启用分层表情包插件")
    config_version: str = Field(default="1.0.0", description="配置版本")


class LayerSelectionConfig(PluginConfigBase):
    """Layer and dedupe settings."""

    __ui_label__: ClassVar[str] = "层级选择"
    __ui_icon__: ClassVar[str] = "list-filter"
    __ui_order__: ClassVar[int] = 1

    catalog_file: str = Field(default=_DEFAULT_CATALOG_FILE, description="表情层资产清单文件名")
    default_active_layers: list[str] = Field(
        default_factory=list,
        description="默认启用层；留空表示所有清单层均可用",
    )
    session_layer_overrides: dict[str, list[str]] = Field(
        default_factory=dict,
        description="按会话覆盖启用层，键为 stream_id，值为层 ID 列表",
    )
    include_unclassified: bool = Field(default=True, description="是否允许未标注表情参与选择")
    recent_history_size: int = Field(default=8, description="每个会话/情绪记录多少个最近选择")
    random_jitter: float = Field(default=0.18, description="打分随机扰动幅度，避免机械轮换")


class LayeredEmojiPluginConfig(PluginConfigBase):
    """Top-level plugin config."""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    layers: LayerSelectionConfig = Field(default_factory=LayerSelectionConfig)


def normalize_hash(value: Any) -> str:
    """Normalize an emoji hash from hook/config payloads."""

    return str(value or "").strip().lower()


def normalize_layer_id(value: Any) -> str:
    """Normalize layer identifiers used in config and commands."""

    return str(value or "").strip()


def normalize_emotion(value: Any) -> str:
    """Normalize an emotion key for recent-history bucketing."""

    return " ".join(str(value or "").strip().lower().split())


def split_emotion_tags(raw_value: Any) -> list[str]:
    """Split comma-like emotion tag text into stable unique tags."""

    if isinstance(raw_value, list):
        tags: list[str] = []
        for item in raw_value:
            tags.extend(split_emotion_tags(item))
    elif isinstance(raw_value, str):
        tags = [part.strip() for part in _EMOTION_SPLIT_RE.split(raw_value) if part.strip()]
    else:
        tags = []

    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        key = normalize_emotion(tag)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(tag)
    return result


def emotion_similarity(target_emotion: str, candidate_tags: Sequence[str]) -> float:
    """Return a 0..1 fit score between target emotion and candidate tags."""

    normalized_target = normalize_emotion(target_emotion)
    if not normalized_target:
        return 0.5

    best_score = 0.0
    for raw_tag in candidate_tags:
        tag = normalize_emotion(raw_tag)
        if not tag:
            continue
        if tag == normalized_target:
            return 1.0
        if tag in normalized_target or normalized_target in tag:
            best_score = max(best_score, 0.82)
            continue
        best_score = max(best_score, SequenceMatcher(None, normalized_target, tag).ratio())
    return best_score


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    return default


def _coerce_weight(value: Any) -> float:
    try:
        weight = float(value)
    except (TypeError, ValueError):
        return 1.0
    if not math.isfinite(weight) or weight <= 0:
        return 1.0
    return weight


def _normalize_layer_list(raw_layers: Any) -> set[str]:
    if isinstance(raw_layers, str):
        values: Iterable[Any] = [raw_layers]
    elif isinstance(raw_layers, Iterable):
        values = raw_layers
    else:
        values = []
    return {normalize_layer_id(value) for value in values if normalize_layer_id(value)}


def load_layer_catalog(path: Path) -> EmojiLayerCatalog:
    """Load ``emoji_layers.toml`` into a normalized catalog."""

    try:
        with path.open("rb") as file_obj:
            raw_catalog = tomllib.load(file_obj)
    except FileNotFoundError:
        return EmojiLayerCatalog()

    raw_layer_items = raw_catalog.get("layers", {}).get("items", [])
    layer_items = raw_layer_items if isinstance(raw_layer_items, list) else []
    layers: dict[str, EmojiLayer] = {}
    for raw_layer in layer_items:
        if not isinstance(raw_layer, dict):
            continue
        layer_id = normalize_layer_id(raw_layer.get("id"))
        if not layer_id:
            continue
        layers[layer_id] = EmojiLayer(
            layer_id=layer_id,
            name=str(raw_layer.get("name") or layer_id).strip() or layer_id,
            weight=_coerce_weight(raw_layer.get("weight")),
            enabled_by_default=_coerce_bool(raw_layer.get("enabled_by_default"), True),
        )

    emoji_layers: dict[str, set[str]] = {}
    raw_emoji_map = raw_catalog.get("emoji_map", {})
    if isinstance(raw_emoji_map, dict):
        for raw_hash, raw_layers in raw_emoji_map.items():
            emoji_hash = normalize_hash(raw_hash)
            if not emoji_hash:
                continue
            mapped_layers = _normalize_layer_list(raw_layers)
            known_layers = {layer_id for layer_id in mapped_layers if layer_id in layers}
            if known_layers:
                emoji_layers[emoji_hash] = known_layers

    return EmojiLayerCatalog(layers=layers, emoji_layers=emoji_layers)


class LayeredEmojiPlugin(MaiBotPlugin):
    """Filter and rerank selected emojis by configured layer and recent usage."""

    config_model = LayeredEmojiPluginConfig

    def __init__(self) -> None:
        super().__init__()
        self._catalog: EmojiLayerCatalog = EmojiLayerCatalog()
        self._catalog_available: bool = False
        self._recent_by_stream_emotion: defaultdict[tuple[str, str], deque[str]] = defaultdict(deque)

    async def on_load(self) -> None:
        self.reload_catalog()

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        del scope, config_data, version
        self.reload_catalog()
        self._trim_recent_history()

    def _get_config_or_default(self) -> LayeredEmojiPluginConfig:
        try:
            config = self.config
        except RuntimeError:
            return LayeredEmojiPluginConfig()
        return config

    def _plugin_dir(self) -> Path:
        return Path(__file__).resolve().parent

    def _catalog_path(self) -> Path:
        configured_file = str(self._get_config_or_default().layers.catalog_file or _DEFAULT_CATALOG_FILE).strip()
        candidate = Path(configured_file)
        if candidate.is_absolute():
            return candidate
        return self._plugin_dir() / candidate

    def reload_catalog(self) -> EmojiLayerCatalog:
        try:
            self._catalog = load_layer_catalog(self._catalog_path())
        except tomllib.TOMLDecodeError:
            self._catalog = EmojiLayerCatalog()
        self._catalog_available = bool(self._catalog.layers)
        return self._catalog

    def _known_layer_ids(self) -> set[str]:
        if not self._catalog.layers:
            return {_UNCLASSIFIED_LAYER_ID}
        return set(self._catalog.layers)

    def _resolve_active_layers(self, stream_id: str) -> set[str]:
        config = self._get_config_or_default().layers
        overrides = config.session_layer_overrides or {}
        if stream_id and stream_id in overrides:
            configured_layers = _normalize_layer_list(overrides.get(stream_id))
        else:
            configured_layers = _normalize_layer_list(config.default_active_layers)
            if not configured_layers:
                configured_layers = self._known_layer_ids()

        active_layers = {layer_id for layer_id in configured_layers if layer_id in self._known_layer_ids()}
        if not active_layers and configured_layers:
            return set()
        if not active_layers:
            active_layers = self._known_layer_ids()
        if config.include_unclassified:
            active_layers.add(_UNCLASSIFIED_LAYER_ID)
        return active_layers

    def _layers_for_emoji(self, emoji_hash: str) -> set[str]:
        layers = self._catalog.get_layers_for_hash(emoji_hash)
        if layers:
            return layers
        return {_UNCLASSIFIED_LAYER_ID}

    def _emoji_tags(self, emoji: Any) -> list[str]:
        description_tags = split_emotion_tags(getattr(emoji, "description", ""))
        emotion_tags = split_emotion_tags(getattr(emoji, "emotion", []))
        result: list[str] = []
        seen: set[str] = set()
        for tag in [*emotion_tags, *description_tags]:
            key = normalize_emotion(tag)
            if not key or key in seen:
                continue
            seen.add(key)
            result.append(tag)
        return result

    def _select_target_emotion(
        self,
        *,
        requested_emotion: str,
        matched_emotion: str,
        selected_emoji: Any,
    ) -> str:
        if normalize_emotion(matched_emotion):
            return matched_emotion
        if normalize_emotion(requested_emotion):
            return requested_emotion
        if isinstance(selected_emoji, dict):
            selected_tags = split_emotion_tags(selected_emoji.get("emotions"))
            if selected_tags:
                return selected_tags[0]
            selected_tags = split_emotion_tags(selected_emoji.get("description"))
            if selected_tags:
                return selected_tags[0]
        return ""

    def _recent_penalty(self, stream_id: str, emotion_key: str, emoji_hash: str) -> float:
        history = self._recent_by_stream_emotion.get((stream_id, emotion_key))
        if not history:
            return 1.0

        penalty = 1.0
        for distance, recent_hash in enumerate(reversed(history), start=1):
            if recent_hash != emoji_hash:
                continue
            penalty += 0.85 / distance
        return penalty

    def _usage_penalty(self, emoji: Any) -> float:
        try:
            query_count = max(0, int(getattr(emoji, "query_count", 0) or 0))
        except (TypeError, ValueError):
            query_count = 0
        return 1.0 + math.log1p(query_count) * 0.08

    def _layer_weight(self, layers: set[str]) -> float:
        weights = [
            self._catalog.layers[layer_id].weight
            for layer_id in layers
            if layer_id in self._catalog.layers
        ]
        return max(weights) if weights else 1.0

    def _score_emoji(
        self,
        emoji: Any,
        *,
        stream_id: str,
        emotion_key: str,
        target_emotion: str,
        selected_hash: str,
        random_source: random.Random | None = None,
    ) -> float:
        emoji_hash = normalize_hash(getattr(emoji, "file_hash", ""))
        tags = self._emoji_tags(emoji)
        base_score = 0.2 + emotion_similarity(target_emotion, tags)
        if selected_hash and emoji_hash == selected_hash:
            base_score += 0.12

        layer_weight = self._layer_weight(self._layers_for_emoji(emoji_hash))
        jitter_amount = max(0.0, float(self._get_config_or_default().layers.random_jitter or 0.0))
        randomizer = random_source or random
        jitter = randomizer.uniform(max(0.05, 1.0 - jitter_amount), 1.0 + jitter_amount)

        return (
            base_score
            * layer_weight
            * jitter
            / self._recent_penalty(stream_id, emotion_key, emoji_hash)
            / self._usage_penalty(emoji)
        )

    @staticmethod
    def _weighted_choice(scored_candidates: list[tuple[Any, float]], random_source: random.Random | None = None) -> Any:
        if not scored_candidates:
            return None
        randomizer = random_source or random
        positive_candidates = [(emoji, max(score, 0.001)) for emoji, score in scored_candidates]
        total_weight = sum(score for _, score in positive_candidates)
        pick = randomizer.uniform(0, total_weight)
        running = 0.0
        for emoji, score in positive_candidates:
            running += score
            if running >= pick:
                return emoji
        return positive_candidates[-1][0]

    def choose_emoji(
        self,
        emojis: Sequence[Any],
        *,
        stream_id: str,
        requested_emotion: str = "",
        matched_emotion: str = "",
        selected_emoji_hash: str = "",
        selected_emoji: Any = None,
        random_source: random.Random | None = None,
    ) -> Any:
        active_layers = self._resolve_active_layers(stream_id)
        if not active_layers:
            return None

        selected_hash = normalize_hash(selected_emoji_hash)
        target_emotion = self._select_target_emotion(
            requested_emotion=requested_emotion,
            matched_emotion=matched_emotion,
            selected_emoji=selected_emoji,
        )
        emotion_key = normalize_emotion(target_emotion) or "default"

        candidates: list[Any] = []
        for emoji in emojis:
            emoji_hash = normalize_hash(getattr(emoji, "file_hash", ""))
            if not emoji_hash:
                continue
            emoji_layers = self._layers_for_emoji(emoji_hash)
            if emoji_layers & active_layers:
                candidates.append(emoji)

        if not candidates:
            return None

        scored = [
            (
                emoji,
                self._score_emoji(
                    emoji,
                    stream_id=stream_id,
                    emotion_key=emotion_key,
                    target_emotion=target_emotion,
                    selected_hash=selected_hash,
                    random_source=random_source,
                ),
            )
            for emoji in candidates
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        shortlist = scored[: min(8, len(scored))]
        return self._weighted_choice(shortlist, random_source=random_source)

    def _record_recent_choice(self, stream_id: str, target_emotion: str, emoji_hash: str) -> None:
        normalized_hash = normalize_hash(emoji_hash)
        if not stream_id or not normalized_hash:
            return
        emotion_key = normalize_emotion(target_emotion) or "default"
        history_size = max(1, int(self._get_config_or_default().layers.recent_history_size or 1))
        history = self._recent_by_stream_emotion[(stream_id, emotion_key)]
        history.append(normalized_hash)
        while len(history) > history_size:
            history.popleft()

    def _trim_recent_history(self) -> None:
        history_size = max(1, int(self._get_config_or_default().layers.recent_history_size or 1))
        for history in self._recent_by_stream_emotion.values():
            while len(history) > history_size:
                history.popleft()

    def _build_modified_kwargs(self, kwargs: dict[str, Any], selected_hash: str, matched_emotion: str) -> dict[str, Any]:
        modified = dict(kwargs)
        modified["selected_emoji_hash"] = selected_hash
        modified["matched_emotion"] = matched_emotion
        return modified

    @HookHandler(
        "emoji.maisaka.after_select",
        name="layered_emoji_after_select",
        description="按表情包层级和同情绪软去重重排已选表情。",
        mode=HookMode.BLOCKING,
        order=HookOrder.NORMAL,
        error_policy=ErrorPolicy.SKIP,
    )
    async def handle_emoji_after_select(
        self,
        stream_id: str = "",
        requested_emotion: str = "",
        reasoning: str = "",
        context_texts: list[str] | None = None,
        sample_size: int = 20,
        selected_emoji: Any = None,
        selected_emoji_hash: str = "",
        matched_emotion: str = "",
        abort_message: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        if not self._get_config_or_default().plugin.enabled:
            return {"action": "continue"}

        if not self._catalog.layers:
            self.reload_catalog()
        if not self._catalog_available:
            return {"action": "continue"}

        from src.emoji_system.emoji_manager import emoji_manager

        selected = self.choose_emoji(
            list(emoji_manager.emojis),
            stream_id=stream_id,
            requested_emotion=requested_emotion,
            matched_emotion=matched_emotion,
            selected_emoji_hash=selected_emoji_hash,
            selected_emoji=selected_emoji,
        )
        if selected is None:
            return {"action": "continue"}

        target_hash = normalize_hash(getattr(selected, "file_hash", ""))
        if not target_hash:
            return {"action": "continue"}

        target_emotion = self._select_target_emotion(
            requested_emotion=requested_emotion,
            matched_emotion=matched_emotion,
            selected_emoji=selected_emoji,
        )
        self._record_recent_choice(stream_id, target_emotion, target_hash)

        original_kwargs = {
            **kwargs,
            "stream_id": stream_id,
            "requested_emotion": requested_emotion,
            "reasoning": reasoning,
            "context_texts": context_texts or [],
            "sample_size": sample_size,
            "selected_emoji": selected_emoji,
            "selected_emoji_hash": selected_emoji_hash,
            "matched_emotion": matched_emotion,
            "abort_message": abort_message,
        }
        return {
            "action": "continue",
            "modified_kwargs": self._build_modified_kwargs(original_kwargs, target_hash, matched_emotion),
        }

    @Command(
        "emoji_layer",
        description="查看或设置当前会话启用的表情包层。",
        pattern=r"^/emoji-layer(?:\s+(?P<layer_command>list|set|clear)(?:\s+(?P<layer_args>.*))?)?\s*$",
    )
    async def handle_emoji_layer_command(
        self,
        stream_id: str = "",
        matched_groups: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        del kwargs
        if not stream_id:
            return False, "无法获取聊天流信息", True
        groups = matched_groups or {}
        command = str(groups.get("layer_command") or "list").strip() or "list"
        args = str(groups.get("layer_args") or "").strip()

        if command == "list":
            message = self._build_layer_list_message(stream_id)
            await self.ctx.send.text(message, stream_id)
            return True, "已发送表情包层列表", True
        if command == "clear":
            await self._set_session_layers(stream_id, None)
            await self.ctx.send.text("已清空当前会话的表情包层覆盖，恢复默认策略。", stream_id)
            return True, "已清空表情包层覆盖", True
        if command == "set":
            layer_ids = self._parse_layer_args(args)
            valid_layers, invalid_layers = self._validate_command_layers(layer_ids)
            if invalid_layers:
                await self.ctx.send.text(f"未知表情包层: {', '.join(invalid_layers)}", stream_id)
                return False, "存在未知表情包层", True
            if not valid_layers:
                await self.ctx.send.text("请提供至少一个表情包层 ID。", stream_id)
                return False, "缺少表情包层 ID", True
            await self._set_session_layers(stream_id, valid_layers)
            await self.ctx.send.text(f"当前会话表情包层已设置为: {', '.join(valid_layers)}", stream_id)
            return True, "已设置表情包层", True

        await self.ctx.send.text("用法: /emoji-layer list | set <layer...> | clear", stream_id)
        return False, "命令不合法", True

    @staticmethod
    def _parse_layer_args(args: str) -> list[str]:
        try:
            raw_parts = shlex.split(args)
        except ValueError:
            raw_parts = args.split()
        return [normalize_layer_id(part) for part in raw_parts if normalize_layer_id(part)]

    def _validate_command_layers(self, layer_ids: Sequence[str]) -> tuple[list[str], list[str]]:
        known_layers = self._known_layer_ids()
        valid: list[str] = []
        invalid: list[str] = []
        for layer_id in layer_ids:
            if layer_id not in known_layers:
                invalid.append(layer_id)
            elif layer_id not in valid:
                valid.append(layer_id)
        return valid, invalid

    async def _set_session_layers(self, stream_id: str, layer_ids: Sequence[str] | None) -> None:
        config = self._get_config_or_default()
        overrides = dict(config.layers.session_layer_overrides or {})
        if layer_ids is None:
            overrides.pop(stream_id, None)
        else:
            overrides[stream_id] = list(layer_ids)
        config.layers.session_layer_overrides = overrides

        call_capability = getattr(self.ctx, "call_capability", None)
        if callable(call_capability):
            await call_capability(
                "component.update_plugin_config",
                plugin_name=_PLUGIN_ID,
                key="layers.session_layer_overrides",
                value=overrides,
            )

    def _build_layer_list_message(self, stream_id: str) -> str:
        self.reload_catalog()
        active_layers = self._resolve_active_layers(stream_id)
        overrides = self._get_config_or_default().layers.session_layer_overrides or {}
        mode = "当前会话覆盖" if stream_id in overrides else "默认策略"

        lines = [f"表情包层 ({mode}):"]
        for layer_id in sorted(self._catalog.layers):
            layer = self._catalog.layers[layer_id]
            marker = "*" if layer_id in active_layers else "-"
            lines.append(f"{marker} {layer.layer_id} - {layer.name} (weight={layer.weight:g})")
        if self._get_config_or_default().layers.include_unclassified:
            marker = "*" if _UNCLASSIFIED_LAYER_ID in active_layers else "-"
            lines.append(f"{marker} {_UNCLASSIFIED_LAYER_ID} - 未标注表情")
        return "\n".join(lines)


def create_plugin() -> LayeredEmojiPlugin:
    """Create the plugin instance."""

    return LayeredEmojiPlugin()
