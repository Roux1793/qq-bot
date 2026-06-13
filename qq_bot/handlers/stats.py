"""统计命令处理"""
from ..db import get_stats
from ..fetch import _sync_to_db as sync_to_db
from ..send import send_group_msg


async def handle_stats(ws, group_id):
    await send_group_msg(ws, group_id, "正在同步并统计...")
    await sync_to_db(group_id)
    stats = get_stats(group_id)
    if stats["total"] == 0:
        await send_group_msg(ws, group_id, "暂无群聊数据~")
        return

    lines = [f"📊 群聊统计 | 已收录 {stats['days']} 天，共 {stats['total']} 条", ""]
    if stats["top_users"]:
        lines.append("🏆 话痨排行：")
        medals = ["🥇", "🥈", "🥉"]
        for i, (name, cnt) in enumerate(stats["top_users"][:10]):
            prefix = medals[i] if i < 3 else f"{i + 1}."
            lines.append(f"  {prefix} {name}: {cnt} 条 ({cnt / stats['total'] * 100:.1f}%)")
        lines.append("")
    if stats["hourly"]:
        peak = max(stats["hourly"], key=lambda x: x[1])
        dead = min(stats["hourly"], key=lambda x: x[1])
        lines.append(f"⏰ 最活跃: {peak[0]}:00 ({peak[1]}条) | 最冷清: {dead[0]}:00 ({dead[1]}条)")
        lines.append("")
    if len(stats["daily"]) >= 2:
        recent = stats["daily"][:7]
        avg = sum(c for _, c in recent) / len(recent)
        best = max(recent, key=lambda x: x[1])
        lines.append(f"📅 近7天日均 {avg:.0f} 条 | 最热闹: {best[0]} ({best[1]} 条)")

    await send_group_msg(ws, group_id, "\n".join(lines))
    print(f"[群{group_id}] 统计完成 ({stats['total']} 条)")
