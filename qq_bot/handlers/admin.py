"""管理员命令处理 + 知识库"""
import re

from ..state import silenced_groups
from ..permissions import is_admin, get_persona_for_group
from ..send import send_group_msg, load_auto_reply_rules, save_auto_reply_rules
from ..db import save_knowledge, search_knowledge, query_messages
from ..llm import call_llm
from ..send import save_silenced as do_save_silenced


async def handle_admin(ws, group_id, user_id, cmd):
    # 规则列表 — 全员可查看
    if re.search(r"规则列表|查看规则", cmd):
        rules = load_auto_reply_rules()
        if not rules:
            await send_group_msg(ws, group_id, "暂无自动回复规则。\n管理员可用：@bot 加规则 关键词→回复要求")
            return
        lines = ["📋 自动回复规则："]
        for r in rules:
            lines.append(f"  • 「{r['keyword']}」→ {r['hint']}")
        await send_group_msg(ws, group_id, "\n".join(lines))
        return

    # 以下操作需要管理员权限
    if not is_admin(user_id):
        await send_group_msg(ws, group_id, "权限不足。加规则/删规则/提取知识需要管理员权限。")
        return

    # 加规则
    m = re.search(r"加规则\s*(.+)", cmd)
    if m:
        rule_text = m.group(1).strip()
        if "→" in rule_text:
            kw, hint = rule_text.split("→", 1)
            kw, hint = kw.strip(), hint.strip()
            rules = load_auto_reply_rules()
            rules.append({"keyword": kw, "hint": hint})
            save_auto_reply_rules(rules)
            await send_group_msg(ws, group_id, f"已添加自动回复规则：触发词「{kw}」→ {hint}")
        else:
            await send_group_msg(ws, group_id, "格式：@bot 加规则 关键词→回复要求\n例如：@bot 加规则 晚饭→推荐附近好吃的")
        return

    # 删规则
    m = re.search(r"删规则\s*(.+)", cmd)
    if m:
        kw = m.group(1).strip()
        rules = load_auto_reply_rules()
        before = len(rules)
        rules = [r for r in rules if r.get("keyword") != kw]
        save_auto_reply_rules(rules)
        await send_group_msg(ws, group_id, f"已删除 {before - len(rules)} 条规则（触发词「{kw}」）")
        return

    # 提取知识点
    if re.search(r"提取知识|分析知识", cmd):
        await send_group_msg(ws, group_id, "正在从最近消息中提取知识点...")
        await _extract_knowledge(ws, group_id)
        await send_group_msg(ws, group_id, "知识点提取完成，用「@bot 回忆 XXX」查看")
        return

    await send_group_msg(ws, group_id,
        "⚙️ 管理员命令：\n"
        "• @bot 加规则 关键词→回复要求\n"
        "• @bot 删规则 关键词\n"
        "• @bot 规则列表\n"
        "• @bot 提取知识点")


async def handle_knowledge(ws, group_id, cmd):
    m = re.search(r"回忆\s*(.+)", cmd)
    if m:
        keyword = m.group(1).strip()
        rows = search_knowledge(group_id, keyword, limit=10)
        if not rows:
            await send_group_msg(ws, group_id, f"群聊记忆中没找到关于「{keyword}」的内容~")
            return
        from datetime import datetime
        lines = [f"🧠 群聊记忆中关于「{keyword}」的内容："]
        for kw, fact, src, ca in rows:
            try:
                t = datetime.fromisoformat(ca).strftime("%m/%d")
            except ValueError:
                t = ca[:10]
            src_text = f"（{src}，{t}）" if src != "bot" else f"（{t}）"
            lines.append(f"  • {fact} {src_text}")
        await send_group_msg(ws, group_id, "\n".join(lines))
        return
    if re.search(r"知识点|知识列表", cmd):
        rows = search_knowledge(group_id, "%", limit=20)
        if not rows:
            await send_group_msg(ws, group_id, "暂无群聊知识点~")
            return
        seen = set()
        items = []
        for kw, fact, _, _ in rows:
            if kw not in seen:
                seen.add(kw)
                items.append(f"  • {kw}: {fact[:60]}")
        await send_group_msg(ws, group_id, "🧠 群聊知识点：\n" + "\n".join(items[:15]))
        return
    await send_group_msg(ws, group_id, "用法：@bot 回忆 XXX / 群聊知识点")


async def _extract_knowledge(ws, group_id):
    lines = query_messages(group_id, limit=50)
    if len(lines) < 10:
        return
    chat_log = "\n".join(lines)
    prompt = (
        "从以下群聊记录中提取值得记住的事实，格式每行一条：关键词 | 事实内容\n"
        "例如：晚饭 | 张三说学校门口新开了川菜馆\n"
        "只提取有实际内容的事实，不要提取闲聊和废话。如果没有值得记的，回复 SKIP。\n\n"
        f"{chat_log}"
    )
    result = await call_llm([
        {"role": "system", "content": "你是群聊知识提取器，只提取有价值的事实。"},
        {"role": "user", "content": prompt},
    ], max_tokens=500, temperature=0.1)

    if not result or "SKIP" in result.upper():
        return

    count = 0
    for line in result.strip().split("\n"):
        line = line.strip().lstrip("-•·* ")
        if "|" not in line:
            continue
        parts = line.split("|", 1)
        kw = parts[0].strip()[:50]
        fact = parts[1].strip()[:500]
        if kw and fact:
            save_knowledge(group_id, kw, fact, "bot")
            count += 1
    if count:
        print(f"[知识库] 群{group_id} 提取 {count} 条")
