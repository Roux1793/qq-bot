"""QQ Bot 消息发送 + 数据文件管理 + 工具函数"""
import asyncio
import json
import os
import random
import re
from pathlib import Path

from .config import STICKERS_DIR, STICKER_CHANCE


# ====== 数据文件管理 ======

def load_json(path: Path, default: dict) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


def save_json(path: Path, data: dict):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ====== 消息发送 ======

async def _send_long(ws, action: str, params: dict, text: str):
    """分段发送长消息（>800 字时自动拆分）"""
    parts = [text[i:i + 800] for i in range(0, len(text), 800)]
    for i, part in enumerate(parts):
        if len(parts) > 1:
            part = f"({i + 1}/{len(parts)})\n{part}"
        payload = json.dumps({"action": action, "params": {**params, "message": part}}, ensure_ascii=False)
        await ws.send(payload)
        if i < len(parts) - 1:
            await asyncio.sleep(2)


async def send_private_msg(ws, user_id, text):
    try:
        await _send_long(ws, "send_private_msg", {"user_id": user_id}, text)
    except Exception as e:
        print(f"[私聊发送] 失败: {e}")


async def send_group_msg(ws, group_id, text, reply_to: str = ""):
    try:
        print(f"[发送] 群{group_id}: {text[:80]}")
        await _send_long(ws, "send_group_msg", {"group_id": group_id}, text)
        # Bot 自己的发言 NapCat 不会回传，手动记入上下文缓冲
        _record_own_message(group_id, text, reply_to)
    except Exception as e:
        print(f"[发送] 失败: {e}")


def _record_own_message(group_id: int, text: str, reply_to: str = ""):
    """将 Bot 自己的发言写入群聊缓冲，使其能感知自己说过什么"""
    from datetime import datetime
    from collections import deque
    from .state import msg_buffer, active_persona

    if group_id not in msg_buffer:
        msg_buffer[group_id] = deque(maxlen=60)

    name_key = active_persona.get(group_id, "default")
    personas = load_personas()
    name = personas.get(name_key, {}).get("name", "Bot")

    ts = datetime.now().strftime("%H:%M")
    short_text = text[:200]
    if reply_to:
        msg_buffer[group_id].append(f"[{ts}] {name} →{reply_to}: {short_text}")
    else:
        msg_buffer[group_id].append(f"[{ts}] {name}: {short_text}")


# ====== 表情包 ======

def random_sticker() -> str | None:
    if not STICKERS_DIR.exists():
        return None
    files = [f for f in STICKERS_DIR.iterdir()
             if f.is_file() and f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')]
    if not files:
        return None
    chosen = random.choice(files)
    return f"[CQ:image,file=file:///{chosen.as_posix()}]"


def clean_reply(text: str) -> str:
    text = re.sub(r"[（(][^）)]*[）)]", "", text)
    text = re.sub(r"\*[^*]+\*", "", text)
    text = re.sub(r"【[^】]+】", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text


def maybe_sticker(text: str, group_id: int = 0) -> str:
    # 只在祥子人设时发表情包
    if group_id:
        from .state import active_persona
        if active_persona.get(group_id, "default") != "祥子":
            return text
    cleaned = clean_reply(text)
    if not cleaned:
        cleaned = text
    if random.random() < STICKER_CHANCE:
        sticker = random_sticker()
        if sticker:
            return cleaned + sticker
    return cleaned


# ====== 工具 ======

def load_personas():
    from .config import PERSONA_FILE, DEFAULT_PERSONAS
    personas = load_json(PERSONA_FILE, {})
    if not personas:
        # 首次加载：写入默认人设集，后续可通过 @bot 创建人设 扩展
        personas = dict(DEFAULT_PERSONAS)
        save_json(PERSONA_FILE, personas)
    return personas


def save_personas(data):
    from .config import PERSONA_FILE
    save_json(PERSONA_FILE, data)


# 默认关键词规则（文件丢失时自动重建）
_DEFAULT_AUTO_REPLY_RULES = [
    {"keyword": "几点", "hint": "告诉对方当前时间"},
    {"keyword": "时间", "hint": "告诉对方当前时间"},
    {"keyword": "几号", "hint": "告诉对方当前日期"},
    {"keyword": "日期", "hint": "告诉对方当前日期"},
    {"keyword": "星期几", "hint": "告诉对方今天是星期几"},
    {"keyword": "好无聊", "hint": "推荐一件事做"},
    {"keyword": "没事干", "hint": "推荐一件事做"},
]


def load_auto_reply_rules() -> list[dict]:
    from .config import AUTO_REPLY_FILE
    data = load_json(AUTO_REPLY_FILE, {"rules": []})
    rules = data.get("rules", [])
    if not rules:
        # 文件丢失 → 用默认规则重建
        save_json(AUTO_REPLY_FILE, {"rules": _DEFAULT_AUTO_REPLY_RULES})
        return list(_DEFAULT_AUTO_REPLY_RULES)
    return rules


def save_auto_reply_rules(rules: list[dict]):
    from .config import AUTO_REPLY_FILE
    save_json(AUTO_REPLY_FILE, {"rules": rules})


def load_silenced() -> set[int]:
    from .config import SILENCE_FILE
    data = load_json(SILENCE_FILE, {"groups": []})
    return set(data.get("groups", []))


def save_silenced():
    from .config import SILENCE_FILE
    from .state import silenced_groups
    save_json(SILENCE_FILE, {"groups": list(silenced_groups)})


def load_group_styles() -> dict:
    from .config import GROUP_STYLE_FILE
    return load_json(GROUP_STYLE_FILE, {})


def save_group_styles(data: dict):
    from .config import GROUP_STYLE_FILE
    save_json(GROUP_STYLE_FILE, data)


def get_group_style(group_id):
    styles = load_group_styles()
    return styles.get(str(group_id), {}).get("style_text", "")
