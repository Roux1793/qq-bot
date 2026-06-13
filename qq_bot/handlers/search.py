"""搜索命令处理"""
import re

from ..db import search_messages
from ..fetch import _sync_to_db as sync_to_db
from ..llm import call_llm, SEARCH_PROMPT
from ..permissions import get_persona_for_group
from ..send import send_group_msg


async def handle_search(ws, group_id, cmd):
    keyword = re.sub(r"(搜索|查找|搜)\s*", "", cmd).strip()
    if not keyword or len(keyword) < 1:
        await send_group_msg(ws, group_id, "请指定搜索关键词，例如：@bot 搜索 晚饭")
        return
    if len(keyword) > 30:
        await send_group_msg(ws, group_id, "关键词太长了")
        return

    await send_group_msg(ws, group_id, f"正在搜索「{keyword}」...")
    await sync_to_db(group_id)
    results = search_messages(group_id, keyword, limit=50)

    if len(results) < 1:
        await send_group_msg(ws, group_id, f"没有找到包含「{keyword}」的消息~")
        return

    print(f"[群{group_id}] 搜索「{keyword}」: {len(results)} 条")

    if len(results) <= 5:
        await send_group_msg(ws, group_id, f"🔍 「{keyword}」共 {len(results)} 条：\n" + "\n".join(results))
    else:
        chat_log = "\n".join(results)
        if len(chat_log) > 6000:
            chat_log = chat_log[-6000:]
        persona = get_persona_for_group(group_id)
        content = await call_llm([
            {"role": "system", "content": persona["system_prompt"]},
            {"role": "user", "content": SEARCH_PROMPT.format(keyword=keyword, chat_log=chat_log)},
        ], max_tokens=800)
        if content:
            await send_group_msg(ws, group_id, f"🔍 「{keyword}」共 {len(results)} 条：\n{content}")
        else:
            await send_group_msg(ws, group_id, f"🔍 「{keyword}」共 {len(results)} 条：\n" + "\n".join(results[-15:]))
