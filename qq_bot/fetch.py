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


# ====== 公共分页器 ======

async def _paginate_messages(group_id, target_count, *, use_ws=False):
    """通用分页拉取：循环 5 次，每次 100 条，去重后返回格式化行列表"""
    all_lines, seen = [], set()
    start_seq = 0
    for _ in range(5):
        if not use_ws:
            messages = await _http_get_page(group_id, start_seq)
        else:
            messages = await _ws_get_page(group_id, start_seq)
        if not messages:
            break

        nc = 0
        for line in _format_messages(messages):
            key = line[:60]
            if key not in seen:
                seen.add(key)
                all_lines.append(line)
                nc += 1

        start_seq = _last_seq_from(messages)
        if nc == 0 or len(all_lines) >= target_count:
            break
        await asyncio.sleep(1.5)

    all_lines.reverse()
    if use_ws and all_lines:
        print(f"[拉取] WebSocket 备用通道成功拉取 {len(all_lines)} 条")
    return all_lines


async def _http_get_page(group_id, start_seq):
    try:
        body = {"group_id": group_id, "count": 100}
        if start_seq:
            body["message_seq"] = start_seq
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post("http://127.0.0.1:3000/get_group_msg_history", json=body)
        if r.status_code == 200 and r.json().get("status") == "ok":
            return r.json().get("data", {}).get("messages", [])
    except Exception as e:
        print(f"[拉取] HTTP API 异常: {e}")
    return None


async def _ws_get_page(group_id, start_seq):
    from .ws import call_api
    params = {"group_id": group_id, "count": 100}
    if start_seq:
        params["message_seq"] = start_seq
    result = await call_api("get_group_msg_history", params, timeout=20)
    if result and result.get("status") == "ok":
        return result.get("data", {}).get("messages", [])
    return None


def _last_seq_from(messages):
    if not messages:
        return 0
    last = messages[-1]
    return last.get("message_seq") or last.get("seq") or last.get("message_id", 0)


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


# ====== 公开 API ======

async def fetch_messages(group_id, count, since=None, until=None):
    """统一消息拉取入口。返回 (lines, source) 其中 source 为 'api'/'ws'/'db'"""
    lines = await _paginate_messages(group_id, count, use_ws=False)
    if lines:
        await sync_to_db_cached(group_id, count)
        return _filter_by_time(lines, since, until), 'api'

    lines = await _paginate_messages(group_id, count, use_ws=True)
    if lines:
        await sync_to_db_cached(group_id, count)
        return _filter_by_time(lines, since, until), 'ws'

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
    start_seq = 0
    for _ in range(5):
        messages = await _http_get_page(group_id, start_seq)
        if not messages:
            messages = await _ws_get_page(group_id, start_seq)
        if not messages:
            break

        nc = 0
        for msg in messages:
            mid = msg.get("message_id") or msg.get("message_seq") or msg.get("seq", 0)
            if mid not in seen_ids:
                seen_ids.add(mid)
                all_msgs.append(msg)
                nc += 1

        start_seq = _last_seq_from(messages)
        if nc == 0 or len(all_msgs) >= target_count:
            break
        await asyncio.sleep(1.5)

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
