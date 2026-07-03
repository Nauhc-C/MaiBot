from typing import Any, Dict, List

from src.llm_models.payload_content.message import Message, MessageBuilder, RoleType

LOCAL_MAI_REPLYER_SYSTEM_PROMPT = (
    "请根据给你的思考内容生成一条回复：只输出最终要发送的实际发言内容。"
    "思考内容里的关键事实、关系判断、过错/立场和明确要求不能被泛化或省略；"
    "回复要实事求是地说清楚事实，并在涉及态度时给出当前态度。"
    "可以压缩表达，但不要把具体事实改写成空泛情绪或套话。"
    "如需引用，请遵循上游指引并明确选择是否引用。"
)
LOCAL_MAI_REPLYER_CATCHPHRASE_BLOCK_PROMPT = (
    "这次回复是复读/重放/转述场景，禁止使用 desuwa、desuno、teyo、maa 等尾部口癖。"
    "保持自然、克制、尽量贴近原意，不要额外加个性化结尾。"
)


def resolve_local_mai_replyer_input(reply_reason: str, reply_tool_args: Dict[str, Any] | None = None) -> str:
    """解析本地麦麦 replyer 的 user message 输入。"""

    latest_reason = reply_reason.strip()
    if latest_reason:
        return latest_reason

    reply_guide = str((reply_tool_args or {}).get("reply_guide") or "").strip()
    if any(bool((reply_tool_args or {}).get(marker)) for marker in ("disable_catchphrases", "no_catchphrases", "no_desuwa")):
        if reply_guide:
            return f"{reply_guide}\n\n{LOCAL_MAI_REPLYER_CATCHPHRASE_BLOCK_PROMPT}"
        return LOCAL_MAI_REPLYER_CATCHPHRASE_BLOCK_PROMPT
    if reply_guide:
        return reply_guide

    raise ValueError("本地麦麦 Replyer 需要来自 Planner 的最新推理或 reply_guide，当前均为空")


def build_local_mai_replyer_messages(
    reply_reason: str,
    reply_tool_args: Dict[str, Any] | None = None,
) -> List[Message]:
    """构建本地麦麦 replyer 的独立请求消息。"""

    local_replyer_input = resolve_local_mai_replyer_input(reply_reason, reply_tool_args)

    return [
        MessageBuilder().set_role(RoleType.System).add_text_content(LOCAL_MAI_REPLYER_SYSTEM_PROMPT).build(),
        MessageBuilder().set_role(RoleType.User).add_text_content(local_replyer_input).build(),
    ]
