"""QQ Bot 消息拉取 — HTTP → WebSocket → 本地 DB 三级回退"""
import asyncio
import sqlite3
from datetime import datetime, timedelta

import httpx

from .config import DB_PATH
from .db import query_messages

# 同步缓存：避免短时间内重复拉取
_last_synced: dict[int, datetime] = {}
_SYNC_COOLDOWN = timedelta(seconds=60)


# ====== 消息拉取 ======

def _format_messages(messages):
    lines = []
    for msg in messages:
        s = msg.get("sender", {})
        nick = s.get("card") or s.get("nickname") or str(msg.get("user_id", "?"))
        raw = msg.get("raw_message") or msg.get("message", "")
        if isinstance(raw, list):
            parts = []
            for seg in raw:
                if seg.get("type") == "text":
                    parts.append(seg.get("data", {}).get("text", ""))
            raw = "".join(parts)
        raw = str(raw).strip()
        if not raw:
            continue
        ts = msg.get("time", 0)
        t = datetime.fromtimestamp(ts).strftime("%m/%d %H:%M")
        lines.append(f"[{t}] {nick}: {raw}")
    return lines


async def _fetch_via_http(group_id, count):
    """通过 HTTP API 拉取消息"""
    try:
        body = {"group_id": group_id, "count": count}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post("http://127.0.0.1:3000/get_group_msg_history", json=body)
        if r.status_code == 200 and r.json().get("status") == "ok":
            messages = r.json().get("data", {}).get("messages", [])
            lines = _format_messages(messages)
            lines.reverse()
            return lines
    except Exception as e:
        print(f"[拉取] HTTP API 异常: {e}")
    return []


async def _fetch_via_ws(group_id, count):
    """通过 WebSocket API 拉取消息（备用）"""
    from .ws import call_api
    result = await call_api("get_group_msg_history",
        {"group_id": group_id, "count": count}, timeout=20)
    if result and result.get("status") == "ok":
        messages = result.get("data", {}).get("messages", [])
        lines = _format_messages(messages)
        lines.reverse()
        print(f"[拉取] WebSocket 备用通道成功拉取 {len(lines)} 条")
        return lines
    return []


# ====== 公开 API ======

async def fetch_messages(group_id, count, since=None, until=None):
    """统一消息拉取入口。返回 (lines, source) 其中 source 为 'api'/'ws'/'db'"""
    # HTTP API 一次请求
    lines = await _fetch_via_http(group_id, count)
    if lines:
        await sync_to_db_cached(group_id, count)
        # API 返回不够？用 DB 补齐
        if len(lines) < count:
            db_lines = query_messages(group_id, limit=count, since=since, until=until)
            if len(db_lines) > len(lines):
                # 合并去重：DB 可能比 API 全（API 有时间限制）
                seen = {l[:60] for l in lines}
                for l in db_lines:
                    if l[:60] not in seen:
                        seen.add(l[:60])
                        lines.append(l)
                lines.sort(key=lambda s: s[1:12])
                return lines, 'api+db'
        return _filter_by_time(lines, since, until), 'api'

    # WebSocket 备用
    lines = await _fetch_via_ws(group_id, count)
    if lines:
        await sync_to_db_cached(group_id, count)
        return _filter_by_time(lines, since, until), 'ws'

    # DB 兜底
    lines = query_messages(group_id, limit=count, since=since, until=until)
    return lines, 'db'


async def sync_to_db_cached(group_id, target_count=500):
    """带缓存的同步入口：60 秒内同一群不重复拉取"""
    now = datetime.now()
    last = _last_synced.get(group_id)
    if last and (now - last) < _SYNC_COOLDOWN:
        return 0  # 跳过，刚同步过
    _last_synced[group_id] = now
    return await _sync_to_db(group_id, target_count)


async def _sync_to_db(group_id, target_count=500):
    """从 HTTP/WS 拉取原始消息并写入本地 DB（去重）"""
    all_msgs, seen_ids = [], set()

    # HTTP 一次拉取
    try:
        body = {"group_id": group_id, "count": target_count}
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post("http://127.0.0.1:3000/get_group_msg_history", json=body)
        if r.status_code == 200 and r.json().get("status") == "ok":
            messages = r.json().get("data", {}).get("messages", [])
            for msg in messages:
                mid = msg.get("message_id") or msg.get("message_seq") or 0
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    all_msgs.append(msg)
    except Exception as e:
        print(f"[同步] HTTP 拉取失败: {e}")
        # 尝试 WS 备用
        from .ws import call_api
        result = await call_api("get_group_msg_history",
            {"group_id": group_id, "count": target_count}, timeout=20)
        if result and result.get("status") == "ok":
            for msg in result.get("data", {}).get("messages", []):
                mid = msg.get("message_id") or msg.get("message_seq") or 0
                if mid not in seen_ids:
                    seen_ids.add(mid)
                    all_msgs.append(msg)

    nc = 0
    try:
        db = sqlite3.connect(str(DB_PATH))
        for msg in all_msgs:
            uid = msg.get("user_id", 0)
            sender = msg.get("sender", {})
            nick = sender.get("card") or sender.get("nickname") or str(uid)
            content = msg.get("raw_message") or msg.get("message", "")
            if isinstance(content, list):
                parts = []
                for seg in content:
                    if seg.get("type") == "text":
                        parts.append(seg.get("data", {}).get("text", ""))
                content = "".join(parts)
            content = str(content).strip()
            if not content:
                continue
            ts = msg.get("time", 0)
            ca = datetime.fromtimestamp(ts).isoformat() if ts else datetime.now().isoformat()
            exists = db.execute(
                "SELECT 1 FROM messages WHERE group_id=? AND user_id=? AND created_at=?",
                (group_id, uid, ca)).fetchone()
            if not exists:
                db.execute(
                    "INSERT INTO messages (group_id,user_id,nickname,content,created_at) VALUES (?,?,?,?,?)",
                    (group_id, uid, nick, content, ca))
                nc += 1
        db.commit()
        db.close()
        if nc:
            print(f"[同步] 群{group_id} 新增 {nc} 条")
    except Exception as e:
        print(f"[同步] DB写入失败: {e}")
    return nc


def _filter_by_time(lines, since, until):
    if not since and not until:
        return lines
    filtered = []
    now = datetime.now()
    for line in lines:
        try:
            ts_str = line[1:12]
            month, day = int(ts_str[0:2]), int(ts_str[3:5])
            hour, minute = int(ts_str[6:8]), int(ts_str[9:11])
            dt = datetime(now.year, month, day, hour, minute)
            if dt > now:
                dt = datetime(now.year - 1, month, day, hour, minute)
            iso = dt.isoformat()
            if since and iso < since:
                continue
            if until and iso > until:
                continue
        except (ValueError, IndexError):
            pass
        filtered.append(line)
    return filtered
