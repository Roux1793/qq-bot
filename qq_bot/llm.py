"""QQ Bot LLM 调用 — API 请求、Prompt 模板、总结/解析"""
import re
from datetime import datetime, timedelta

import httpx

from .config import API_KEY, API_BASE, MODEL, HISTORY_FETCH_COUNT, STYLE_LEARN_EXCLUDE_GROUPS, ANTI_AGGRESSION_RULES
from .db import query_messages
from .state import active_persona


def safe_system_prompt(persona: dict) -> str:
    """返回注入反攻击规则后的 system_prompt，供所有 LLM 调用点使用"""
    sp = persona.get("system_prompt", "")
    return sp + "\n\n" + ANTI_AGGRESSION_RULES


# ====== Prompt 模板 ======

SUMMARY_PROMPT = """你是QQ群聊总结助手。请根据以下群聊记录生成详细总结。

{context}群聊记录（{msg_count} 条消息{time_info}{topic_info}）：
---
{chat_log}
---

请按以下格式输出（中文，客观记述，忽略纯表情/广告/复读）：

📌 **话题总结**：逐一列出每个话题，说明讨论内容和结论
🗣 **活跃成员**：发言较多的成员及其主要观点
📊 **讨论趋势**：整体氛围、话题切换节奏
⏱ **时间跨度**：消息覆盖的时间范围"""

SEARCH_PROMPT = """以下是包含关键词 "{keyword}" 的QQ群聊消息。请概括讨论内容并列出关键发言。

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

📝 **总结** — @bot 总结 [今天/昨天/本周/N天/N小时/N条]
🔍 **搜索** — @bot 搜索 XXX
📊 **统计** — @bot 统计
💬 **闲聊** — @bot 随便说点什么
💡 **其他** — @bot help"""

ADMIN_HELP = """⚙️ **管理员命令**

🎭 人设管理
• @bot 切换 — 在人设间来回切换
• @bot 修改人设 [描述] — 用对话修改当前人设
• @bot 人设列表 / 人设详情 XX

🔇 禁言控制
• @bot silence — 停止在该群发言
• @bot 恢复 — 恢复在该群发言
• 私聊发送 群号silence — 远程禁言指定群

📋 规则管理
• @bot 加规则 关键词→回复要求
• @bot 删规则 关键词 / 规则列表

🧠 知识管理
• @bot 回忆 XXX — 查询知识库
• @bot 群聊知识点 — 浏览知识点
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

    from .permissions import get_persona_for_group
    persona = get_persona_for_group(group_id)
    return await call_llm([
        {"role": "system", "content": persona["system_prompt"]},
        {"role": "user", "content": prompt},
    ], max_tokens=2500, timeout=120)


# ====== 命令解析（纯正则） ======

def parse_time_range(text):
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if re.search(r"今天|今日", text):
        return today.isoformat(), None, "今天"
    if re.search(r"昨天|昨日", text):
        y = today - timedelta(days=1)
        return y.isoformat(), (today - timedelta(seconds=1)).isoformat(), "昨天"
    if re.search(r"本周|这周", text):
        mon = today - timedelta(days=today.weekday())
        return mon.isoformat(), None, "本周"
    if re.search(r"上周", text):
        mon = today - timedelta(days=today.weekday() + 7)
        return mon.isoformat(), (mon + timedelta(days=7) - timedelta(seconds=1)).isoformat(), "上周"
    m = re.search(r"(\d+)\s*天", text)
    if m:
        n = int(m.group(1))
        return (today - timedelta(days=n - 1)).isoformat(), None, f"最近{n}天"
    m = re.search(r"(\d+)\s*小时", text)
    if m:
        n = int(m.group(1))
        return (now - timedelta(hours=n)).isoformat(), None, f"最近{n}小时"
    if re.search(r"本月|这个月", text):
        return today.replace(day=1).isoformat(), None, "本月"
    return None, None, ""


def parse_summary_cmd(cmd):
    result = {"count": HISTORY_FETCH_COUNT, "since": None, "until": None, "time_label": "", "topic": ""}
    m = re.search(r"(\d+)\s*条?", cmd)
    if m:
        result["count"] = max(100, min(2000, int(m.group(1))))
    since, until, time_label = parse_time_range(cmd)
    if since:
        result["since"] = since
        result["until"] = until
        result["time_label"] = time_label
        return result
    for pattern in [r"关于(.+?)(?:的|的内容|相关)?$", r"(.+?)相关"]:
        m = re.search(pattern, cmd)
        if m:
            topic = m.group(1).strip()
            if topic and len(topic) < 50:
                result["topic"] = topic
                if not re.search(r"\d+\s*条?", cmd):
                    result["count"] = 500
                result["time_label"] = result["time_label"] or "最近3天"
                result["since"] = (datetime.now() - timedelta(days=3)).isoformat()
                return result
    return result


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
