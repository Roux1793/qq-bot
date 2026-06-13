"""QQ Bot 消息发送 + 数据文件管理 + 工具函数"""
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


# ====== 发送消息 ======

async def send_private_msg(ws, user_id, text):
    try:
        if len(text) > 800:
            parts = [text[i:i + 800] for i in range(0, len(text), 800)]
            for i, part in enumerate(parts):
                prefix = f"({i + 1}/{len(parts)})\n" if len(parts) > 1 else ""
                await ws.send(json.dumps({"action": "send_private_msg",
                    "params": {"user_id": user_id, "message": prefix + part}}, ensure_ascii=False))
                import asyncio
                await asyncio.sleep(2)
        else:
            await ws.send(json.dumps({"action": "send_private_msg",
                "params": {"user_id": user_id, "message": text}}, ensure_ascii=False))
    except Exception as e:
        print(f"[私聊发送] 失败: {e}")


async def send_group_msg(ws, group_id, text):
    try:
        print(f"[发送] 群{group_id}: {text[:80]}")
        if len(text) > 800:
            parts = [text[i:i + 800] for i in range(0, len(text), 800)]
            for i, part in enumerate(parts):
                prefix = f"({i + 1}/{len(parts)})\n" if len(parts) > 1 else ""
                payload = json.dumps({"action": "send_group_msg",
                    "params": {"group_id": group_id, "message": prefix + part}}, ensure_ascii=False)
                await ws.send(payload)
                import asyncio
                await asyncio.sleep(2)
        else:
            payload = json.dumps({"action": "send_group_msg",
                "params": {"group_id": group_id, "message": text}}, ensure_ascii=False)
            await ws.send(payload)
    except Exception as e:
        print(f"[发送] 失败: {e}")


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


def maybe_sticker(text: str) -> str:
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


def load_auto_reply_rules() -> list[dict]:
    from .config import AUTO_REPLY_FILE
    return load_json(AUTO_REPLY_FILE, {"rules": []}).get("rules", [])


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
