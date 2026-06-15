"""LLM 对话构建 — 系统提示词组装、知识库/搜索集成、上下文构建"""
import re
from collections import deque

from ..config import (GROUP_CONTEXT_LINES, MAX_REPLY_TOKENS, ANTI_AGGRESSION_RULES)
from ..state import msg_buffer, conv_history
from ..permissions import get_persona_for_group
from ..knowledge_search import search as kb_search, should_query_kb, format_kb_results, build_grounding_prompt
from ..web_search import search_web, should_search, format_search_results


async def build_conversation(
    group_id: int,
    user_id: int,
    nickname: str,
    cmd: str,
    *,
    reply_context: str = "",
) -> tuple[list[dict], int]:
    """构建完整的 LLM messages 列表和动态 max_tokens。

    返回 (messages, dyn_tokens)，调用方只需 call_llm(messages, max_tokens=dyn_tokens, ...)。
    """

    # ── 知识库检索（BanG Dream 相关问题优先）──
    kb_context = ""
    kb_grounding = ""
    kb_query = should_query_kb(cmd)
    if kb_query:
        print(f"[知识库] 触发检索: 「{kb_query}」")
        kb_results = kb_search(kb_query, top_n=3)
        kb_context = format_kb_results(kb_results)
        kb_grounding = build_grounding_prompt(kb_results)

    # ── 联网搜索（按需触发，作为补充）──
    search_context = ""
    search_query = should_search(cmd)
    if search_query:
        print(f"[搜索] 触发搜索: 「{search_query}」")
        results = await search_web(search_query, num=5)
        search_context = format_search_results(results)

    # ── 系统消息：人设 + 说话人 + 跨群隔离 + 反攻击 ──
    persona = get_persona_for_group(group_id)
    system_msg = (
        persona["system_prompt"]
        + f"\n\n## 当前对话者\n"
        + f"正在对你说话的人是「{nickname}」(QQ:{user_id})。你必须回复ta。\n"
        + f"【重要】用QQ号区分人：群里有昵称相似的人时，靠QQ号（{user_id}）来区分，不要搞混。\n"
        + f"【重要】跨群隔离：你在这个群的对话和你与其他群的对话完全独立。不要把在别的群发生的事带到这个群来。\n\n"
        + ANTI_AGGRESSION_RULES
    )
    if kb_context:
        system_msg += f"\n\n{kb_context}"
    if kb_grounding:
        system_msg += f"\n\n{kb_grounding}"
    if search_context:
        system_msg += f"\n\n{search_context}"
    messages = [{"role": "system", "content": system_msg}]

    # ── 对话历史（标注说话人）──
    history_key = (group_id, user_id)
    history = conv_history.get(history_key)
    if history:
        for h in list(history):
            if h["role"] == "user":
                speaker = h.get("name", str(user_id))
                messages.append({"role": "user", "content": f"「{speaker}」说：{h['content']}"})
            else:
                messages.append({"role": h["role"], "content": h["content"]})

    # ── 硬提醒（recency bias：放在最后，覆盖 LLM 的幻觉和冲动倾向）──
    HARD_REMINDER = (
        "\n\n[硬事实提醒——这些比你自己的判断更重要，必须遵守]"
        "\n• 你的生日是2005年2月14日。禁止说2007、2008或任何其他年份。"
        "\n• 你永远是15岁。禁止用当前年份计算年龄。"
        "\n• 你是大小姐，优雅但有锋芒。禁止脏话，但不必过分温柔讨好。冷淡≠软弱。"
        "\n• 被挑衅时冷淡回应或无视。保持尊严，不低声下气，也不撒泼骂街。"
    )

    # ── 群聊环境（扩展上下文 + 标注所有说话人）──
    buf = list(msg_buffer.get(group_id, deque(maxlen=60)))
    recent = buf[-GROUP_CONTEXT_LINES:] if len(buf) >= GROUP_CONTEXT_LINES else buf
    if recent:
        # 组装群聊上下文，标注说话人
        lines = []
        for line in recent:
            m = re.match(r"\[\d\d:\d\d\] (.+?):", line)
            speaker_in_line = m.group(1) if m else ""
            if speaker_in_line == nickname:
                lines.append(line + f"  ← 当前在对你说话 (QQ:{user_id})")
            elif speaker_in_line:
                lines.append(line)
            else:
                lines.append(line)

        # 识别上下文中有哪些不同的人
        speakers_in_context = set()
        for line in recent:
            m = re.match(r"\[\d\d:\d\d\] (.+?):", line)
            if m:
                speakers_in_context.add(m.group(1))

        ctx_text = (
            f"## 群聊实时环境（共{len(lines)}条，说话人：{', '.join(speakers_in_context)}）\n"
            + "\n".join(lines)
            + f"\n\n## 你的任务\n"
            + f"「{nickname}」在对你说话"
            + (f"。{reply_context}" if reply_context else "")
            + f"。请综合群聊环境和你的对话历史，自然地回复。\n"
            + f"回复要求：像真人聊天一样，长短由内容决定，不要客套模板。"
            + HARD_REMINDER
        )
        messages.append({"role": "user", "content": f"{ctx_text}\n{cmd}"})
    else:
        msg_text = f"「{nickname}」对你说：{cmd}"
        if reply_context:
            msg_text = f"「{nickname}」{reply_context}：{cmd}"
        messages.append({"role": "user", "content": msg_text + HARD_REMINDER})

    # ── 自适应 max_tokens ──
    ctx_len = len(cmd or "") + sum(len(m["content"]) for m in messages)
    if ctx_len < 500:
        dyn_tokens = 300
    elif ctx_len < 1500:
        dyn_tokens = 500
    elif ctx_len < 3000:
        dyn_tokens = 700
    else:
        dyn_tokens = MAX_REPLY_TOKENS

    return messages, dyn_tokens
