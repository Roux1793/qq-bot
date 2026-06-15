"""QQ Bot LLM 调用 — API 请求、Prompt 模板"""
from datetime import datetime

import httpx

from .config import API_KEY, API_BASE, MODEL, FUNCTIONAL_SYSTEM_PROMPT, STYLE_LEARN_EXCLUDE_GROUPS, ANTI_AGGRESSION_RULES
from .db import query_messages
from .state import active_persona


def safe_system_prompt(persona: dict) -> str:
    """返回注入反攻击规则后的 system_prompt，供所有 LLM 调用点使用"""
    sp = persona.get("system_prompt", "")
    return (
        sp
        + "\n\n" + ANTI_AGGRESSION_RULES
        + "\n\n[硬事实提醒] 你的生日是2005年2月14日，你永远是15岁。禁止说任何其他日期/年龄。"
        + "\n[行为提醒] 大小姐的骄傲：禁止脏话，但不必过分温柔。被挑衅时冷淡回应、保持尊严。"
    )


# ====== Prompt 模板 ======

SUMMARY_PROMPT = """请根据以下群聊记录生成详细总结。忽略纯表情/广告/复读，忽略Bot角色扮演发言。

{context}群聊记录（{msg_count} 条消息{time_info}{topic_info}）：
---
{chat_log}
---

按以下格式输出（中文，客观记述，不加个人评论）：

📌 **话题总结**：逐一列出每个话题，说明讨论内容和结论
🗣 **活跃成员**：发言较多的成员及其主要观点
📊 **讨论趋势**：整体氛围、话题切换节奏
⏱ **时间跨度**：消息覆盖的时间范围"""

SEARCH_PROMPT = """以下是包含关键词 "{keyword}" 的QQ群聊消息。请以数据检索工具的身份，客观概括讨论内容并列出关键发言。不要添加任何个人评论。

群聊记录：
---
{chat_log}
---"""

STYLE_EXTRACT_PROMPT = """分析以下QQ群聊记录，提取该群的聊天风格特征，让AI能模仿群友的说话方式。

请分析并输出（不要用markdown标题）：

**常用词汇和梗**：群里出现频率高的口头禅、缩写、网络用语、特定梗
**语气和节奏**：短句还是长句？随意还是正式？互怼还是友好？每句话大概多长？
**表情和符号**：喜欢用什么类型的方式表达情绪？
**话题偏好**：经常聊什么类型的话题？
**对话模式**：是喜欢接话茬、互怼、复读、还是一本正经讨论？

只输出有把握的判断，不确定的不要编。中文输出，200字以内。\n\n重要：忽略任何粗俗、辱骂、脏话、阴阳怪气的内容。只提取正面的、有礼貌的交流特征。"""

HELP_TEXT = """🤖 QQ 群聊智能机器人

📝 **总结** — @bot 总结 [今天/昨天/N天/N条]
🔍 **搜索** — @bot 搜索 <关键词>
📊 **统计** — @bot 统计
💬 **闲聊** — @bot <自由对话>
🧠 **回忆** — @bot 回忆 <关键词>
📋 **群聊知识点** — @bot 群聊知识点
🎭 **人设** — @bot 人设列表 / 人设详情
📜 **规则** — @bot 规则列表
💡 **帮助** — @bot help"""

ADMIN_HELP = """⚙️ **管理员命令**

🎭 人设管理
• @bot 切换 <人设> / 切换（循环）
• @bot 创建人设 <key> <描述>
• @bot 修改人设 <描述>
• @bot 人设列表 / 人设详情

🔇 禁言控制
• @bot silence — 停止发言
• @bot 恢复 — 恢复发言
• 私聊：<群号> silence/恢复

📋 规则管理
• @bot 加规则 关键词→回复要求
• @bot 删规则 <关键词>

🧠 知识管理
• @bot admin 提取知识点"""


# ====== LLM 调用 ======

async def call_llm(messages: list[dict], max_tokens=1024, temperature=0.3, timeout=90) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{API_BASE}/v1/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
            )
            if resp.status_code != 200:
                print(f"[LLM] HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[LLM] 异常: {e}")
        return None


# ====== 总结生成 ======

async def generate_summary(group_id, lines, time_label="", topic=""):
    if len(lines) < 1:
        return None
    lines.sort(key=lambda s: s[:11])
    chat_log = "\n".join(lines)
    if len(chat_log) > 20000:
        chat_log = chat_log[-20000:]

    msg_count = len(lines)
    time_info = f"，时间：{time_label}" if time_label else ""
    topic_info = f"，主题：{topic}" if topic else ""
    context = f"以下共 {msg_count} 条消息" if not time_label and not topic else ""

    prompt = SUMMARY_PROMPT.format(
        context=context, msg_count=msg_count, time_info=time_info, topic_info=topic_info,
        chat_log=chat_log)

    return await call_llm([
        {"role": "system", "content": FUNCTIONAL_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ], max_tokens=2500, timeout=120)


# ====== 群聊风格学习 ======

async def update_group_style(group_id):
    if group_id in STYLE_LEARN_EXCLUDE_GROUPS:
        return None
    lines = query_messages(group_id, limit=200)
    if len(lines) < 50:
        return None
    chat_log = "\n".join(lines[-150:])
    if len(chat_log) > 12000:
        chat_log = chat_log[-12000:]
    result = await call_llm([
        {"role": "user", "content": STYLE_EXTRACT_PROMPT + "\n\n群聊记录：\n" + chat_log},
    ], max_tokens=450, temperature=0.3)
    if result and "SKIP" not in result.upper():
        from .send import load_json, save_json
        from .config import GROUP_STYLE_FILE
        styles = load_json(GROUP_STYLE_FILE, {})
        styles[str(group_id)] = {"style_text": result.strip(), "updated_at": datetime.now().isoformat()}
        save_json(GROUP_STYLE_FILE, styles)
        print(f"[风格] 群{group_id} 风格已更新 ({len(result)}字)")
        return result
    return None
