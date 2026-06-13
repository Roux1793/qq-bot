"""总结命令处理"""
from datetime import datetime, timedelta

from ..config import HISTORY_FETCH_COUNT
from ..state import last_summary
from ..permissions import is_admin
from ..fetch import fetch_messages
from ..llm import parse_summary_cmd, generate_summary
from ..send import send_group_msg


async def handle_summary(ws, group_id, user_id, cmd, now):
    if group_id in last_summary:
        cooldown = timedelta(seconds=30) if is_admin(user_id) else timedelta(minutes=5)
        if (now - last_summary[group_id]) < cooldown:
            await send_group_msg(ws, group_id,
                "刚总结过，稍等几秒~" if is_admin(user_id) else "刚总结过，稍等几分钟~")
            return
    last_summary[group_id] = now

    params = parse_summary_cmd(cmd)
    fetch_count = params["count"]
    since = params["since"]
    until = params["until"]
    time_label = params["time_label"]
    topic = params["topic"]

    if topic:
        await send_group_msg(ws, group_id, f"正在拉取 {fetch_count} 条消息，总结关于「{topic}」的内容...")
    elif time_label:
        await send_group_msg(ws, group_id, f"正在整理{time_label}的群聊要点（目标 {fetch_count} 条）...")
    else:
        await send_group_msg(ws, group_id, f"正在从QQ拉取最近 {fetch_count} 条消息...")

    lines, source = await fetch_messages(group_id, fetch_count, since=since, until=until)

    source_hint = ""
    if source == 'db':
        source_hint = "（⚠️ QQ API 不可用，使用本地缓存，可能不是最新）"
    elif source == 'ws':
        source_hint = "（已通过备用通道拉取）"

    print(f"[群{group_id}] 总结: {len(lines)} 条 (source={source})"
          + (f" ({time_label})" if time_label else "")
          + (f" topic={topic}" if topic else ""))

    if len(lines) < 1:
        await send_group_msg(ws, group_id,
            f"没有找到{time_label + '的' if time_label else ''}群聊记录~{source_hint}")
        return

    if source_hint:
        await send_group_msg(ws, group_id, source_hint)

    summary = await generate_summary(group_id, lines, time_label=time_label, topic=topic)

    if summary:
        await send_group_msg(ws, group_id, summary)
    else:
        await send_group_msg(ws, group_id, "总结失败，请稍后重试。")
