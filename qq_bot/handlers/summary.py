"""总结命令处理 + 时间范围解析"""
import re
from datetime import datetime, timedelta

from ..config import HISTORY_FETCH_COUNT
from ..state import last_summary
from ..permissions import is_admin
from ..fetch import fetch_messages
from ..llm import generate_summary
from ..send import send_group_msg


# ====== 时间/参数解析 ======

def parse_time_range(text: str) -> tuple[str | None, str | None, str]:
    """从文本中提取时间范围，返回 (since_iso, until_iso, label)"""
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


def parse_summary_cmd(cmd: str) -> dict:
    """解析总结指令，返回 {count, since, until, time_label, topic}"""
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


# ====== 总结处理 ======

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
