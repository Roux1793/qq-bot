"""QQ Bot SQLite 数据库操作 — 消息 + 知识库"""
import sqlite3
from datetime import datetime, timedelta
from .config import DB_PATH, MSG_RETENTION_DAYS


def init_db():
    db = sqlite3.connect(str(DB_PATH))
    db.execute("""CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
        nickname TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_group_time ON messages(group_id, created_at)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_group_content ON messages(group_id, content)")
    db.execute("""CREATE TABLE IF NOT EXISTS knowledge (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL, keyword TEXT NOT NULL,
        fact TEXT NOT NULL, source_nickname TEXT, created_at TEXT NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_kw_group ON knowledge(group_id, keyword)")
    db.commit()
    db.close()
    print(f"[DB] 已就绪: {DB_PATH}")


def save_message(group_id, user_id, nickname, content):
    try:
        db = sqlite3.connect(str(DB_PATH))
        db.execute("INSERT INTO messages (group_id,user_id,nickname,content,created_at) VALUES (?,?,?,?,?)",
                   (group_id, user_id, nickname, content, datetime.now().isoformat()))
        db.commit()
        db.close()
    except Exception as e:
        print(f"[DB] 写入失败: {e}")


def query_messages(group_id, limit=500, since=None, until=None):
    try:
        db = sqlite3.connect(str(DB_PATH))
        sql = "SELECT nickname,content,created_at FROM messages WHERE group_id=?"
        params = [group_id]
        if since:
            sql += " AND created_at>=?"; params.append(since)
        if until:
            sql += " AND created_at<=?"; params.append(until)
        sql += " ORDER BY created_at DESC LIMIT ?"; params.append(limit)
        rows = db.execute(sql, params).fetchall()
        db.close()
        lines = []
        for n, c, t in reversed(rows):
            try:
                ts = datetime.fromisoformat(t).strftime("%m/%d %H:%M")
            except ValueError:
                ts = t[:16]
            lines.append(f"[{ts}] {n}: {c}")
        return lines
    except Exception as e:
        print(f"[DB] 查询失败: {e}")
        return []


def search_messages(group_id, keyword, limit=30):
    try:
        db = sqlite3.connect(str(DB_PATH))
        rows = db.execute(
            "SELECT nickname,content,created_at FROM messages WHERE group_id=? AND content LIKE ? ORDER BY created_at DESC LIMIT ?",
            (group_id, f"%{keyword}%", limit)).fetchall()
        db.close()
        lines = []
        for n, c, t in reversed(rows):
            try:
                ts = datetime.fromisoformat(t).strftime("%m/%d %H:%M")
            except ValueError:
                ts = t[:16]
            lines.append(f"[{ts}] {n}: {c}")
        return lines
    except Exception as e:
        print(f"[DB] 搜索失败: {e}")
        return []


def save_knowledge(group_id, keyword, fact, source_nickname):
    try:
        db = sqlite3.connect(str(DB_PATH))
        db.execute("INSERT INTO knowledge (group_id,keyword,fact,source_nickname,created_at) VALUES (?,?,?,?,?)",
                   (group_id, keyword, fact, source_nickname, datetime.now().isoformat()))
        db.commit()
        db.close()
    except Exception as e:
        print(f"[知识库] 写入失败: {e}")


def search_knowledge(group_id, keyword, limit=10):
    try:
        db = sqlite3.connect(str(DB_PATH))
        rows = db.execute(
            "SELECT keyword,fact,source_nickname,created_at FROM knowledge WHERE group_id=? AND (keyword LIKE ? OR fact LIKE ?) ORDER BY created_at DESC LIMIT ?",
            (group_id, f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
        db.close()
        return rows
    except Exception as e:
        print(f"[知识库] 查询失败: {e}")
        return []


def get_stats(group_id):
    try:
        db = sqlite3.connect(str(DB_PATH))
        total = db.execute("SELECT COUNT(*) FROM messages WHERE group_id=?", (group_id,)).fetchone()[0]
        if total == 0:
            db.close()
            return {"total": 0, "top_users": [], "hourly": [], "daily": [], "days": 0}
        top_users = db.execute(
            "SELECT nickname,COUNT(*) c FROM messages WHERE group_id=? GROUP BY user_id ORDER BY c DESC LIMIT 10",
            (group_id,)).fetchall()
        hourly = db.execute(
            "SELECT substr(created_at,12,2) h,COUNT(*) c FROM messages WHERE group_id=? GROUP BY h ORDER BY h",
            (group_id,)).fetchall()
        daily = db.execute(
            "SELECT substr(created_at,1,10) d,COUNT(*) c FROM messages WHERE group_id=? GROUP BY d ORDER BY d DESC LIMIT 14",
            (group_id,)).fetchall()
        first = db.execute("SELECT created_at FROM messages WHERE group_id=? ORDER BY created_at ASC LIMIT 1",
                           (group_id,)).fetchone()
        days = 1
        if first:
            try:
                days = max(1, (datetime.now() - datetime.fromisoformat(first[0])).days + 1)
            except ValueError:
                pass
        db.close()
        return {"total": total, "top_users": top_users, "hourly": hourly, "daily": daily, "days": days}
    except Exception as e:
        print(f"[DB] 统计失败: {e}")
        return {"total": 0, "top_users": [], "hourly": [], "daily": [], "days": 0}


def cleanup_old_messages():
    cutoff = (datetime.now() - timedelta(days=MSG_RETENTION_DAYS)).isoformat()
    try:
        db = sqlite3.connect(str(DB_PATH))
        d1 = db.execute("DELETE FROM messages WHERE created_at<?", (cutoff,)).rowcount
        d2 = db.execute("DELETE FROM knowledge WHERE created_at<?", (cutoff,)).rowcount
        db.commit(); db.close()
        if d1 or d2:
            print(f"[DB] 清理 {d1} 条消息 + {d2} 条知识")
    except Exception as e:
        print(f"[DB] 清理失败: {e}")


def db_stats():
    try:
        db = sqlite3.connect(str(DB_PATH))
        total = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        groups = db.execute("SELECT group_id,COUNT(*) c FROM messages GROUP BY group_id ORDER BY c DESC").fetchall()
        kw_total = db.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
        db.close()
        parts = [f"消息 {total} 条 | 知识 {kw_total} 条"]
        for g, c in groups:
            parts.append(f"  群{g}: {c} 条")
        return "\n".join(parts)
    except Exception:
        return "统计失败"
