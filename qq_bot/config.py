"""QQ Bot 全局配置 — 路径、常量、环境变量"""
import os
from pathlib import Path

# 加载 .env 文件
_ENV_FILE = Path("/home/roux/.env")
if _ENV_FILE.exists():
    for _line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            os.environ.setdefault(_key.strip(), _val.strip())
    print(f"[配置] 已加载 {_ENV_FILE}")

# === 路径 ===
HOME = Path("/home/roux")
DB_PATH = HOME / "chat_history.db"
AUTO_REPLY_FILE = HOME / "auto_reply.json"
PERSONA_FILE = HOME / "personas.json"
ACTIVE_PERSONA_FILE = HOME / "active_personas.json"
PERMS_FILE = HOME / "group_perms.json"
STICKERS_DIR = Path("/home/roux/stickers")
GROUP_STYLE_FILE = HOME / "group_styles.json"
SILENCE_FILE = HOME / "silenced_groups.json"
QQ_LOG = HOME / "qq.log"
BRIDGE_LOG = HOME / "bridge.log"

# === NapCat WebSocket/HTTP ===
WS_URL = os.environ.get("WS_URL", "ws://127.0.0.1:3001")

# === LLM API ===
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "your-api-key-here")
API_BASE = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

# === 管理员 ===
ADMIN_QQ = [
    int(q.strip()) for q in
    os.environ.get("ADMIN_QQ", "").split(",") if q.strip()
]

# === 数据保留 ===
MSG_RETENTION_DAYS = 14
HISTORY_FETCH_COUNT = 100
STYLE_UPDATE_INTERVAL = 300

# === 自动插话 ===
AUTO_CHIME_EVERY = 80
AUTO_CHIME_COOLDOWN = 1800
AUTO_REPLY_COOLDOWN = 300
QUICK_CHIME_EVERY = 10
QUICK_CHIME_CHANCE = 0.5
QUICK_CHIME_COOLDOWN = 600

# === 冷群复活 ===
REVIVE_SILENCE_MINUTES = 180
REVIVE_CHECK_INTERVAL = 1800
REVIVE_DAY_START = 8
REVIVE_DAY_END = 22
REVIVE_EXCLUDE_GROUPS = {152431674}

# === 群聊特殊配置 ===
STYLE_LEARN_EXCLUDE_GROUPS = {462665991}
GROUP_MAX_MSG_LENGTH: dict[int, int] = {462665991: 15}

# === 表情包 ===
STICKER_CHANCE = 0.15

# === 假死检测 ===
HEALTH_CHECK_INTERVAL = 90
HEALTH_CHECK_MAX_FAILURES = 3
HEALTH_SILENCE_WARN_MINUTES = 60
RESTART_COOLDOWN = 600
QQ_PROCESS_PATTERN = "opt/QQ/qq"
QQ_RESTART_CMD = (
    "setsid /root/Napcat/opt/QQ/qq --no-sandbox --disable-gpu "
    "-q 2712841947 > ~/qq.log 2>&1 &"
)

# === 多轮对话 ===
MAX_CONV_TURNS = 8

# === 默认人设 ===
DEFAULT_PERSONAS = {
    "default": {
        "name": "小助手",
        "system_prompt": "你是QQ群聊助手小助手，性格温和耐心。用简洁友好的中文回复群友，适当使用表情符号活跃气氛。回答问题时条理清晰，遇到不懂的诚实说不知道。",
        "chime_prompt": "下面是一段QQ群聊。请判断：你现在是否应该发言？\n"
                        "发言条件：话题和你相关、群友有疑问没人答、或者你能提供有价值的信息。\n"
                        "如果应该发言，用一两句话自然地说出来。如果不该，只回复 SKIP。\n\n"
                        "{chat_log}",
    },
    "tsundere": {
        "name": "傲娇猫娘",
        "system_prompt": "你是一只傲娇猫娘，说话带「喵」的口癖。嘴上总说不关心、不帮忙，但最后还是心软地帮了。说话风格：先傲后娇，偶尔毒舌但不伤人。回复控制在 2-3 句话。",
        "chime_prompt": "下面是一段QQ群聊。作为一只傲娇猫娘，判断你是否该插话。\n"
                        "如果群友在讨论有趣的话题或者有人需要帮助，就用傲娇的语气插一句。\n"
                        "如果不想插话，只回复 SKIP。\n\n{chat_log}",
    },
    "chuunibyou": {
        "name": "中二病魔王",
        "system_prompt": "你是来自暗影界的魔王「Dark Flame Master」，被封印在QQ群里。说话中二病十足，动不动就解放封印、召唤暗炎、开邪王真眼。但本质是个好人，用中二的方式认真回答问题。回复 2-3 句话，必须包含至少一个中二元素。",
        "chime_prompt": "下面是一段QQ群聊。你作为被封印的魔王，判断凡人是否在讨论值得你降临的话题。\n"
                        "如果该插话，用你的中二风格说一句。如果不该，回复 SKIP。\n\n{chat_log}",
    },
}

# === 群权限默认值 ===
DEFAULT_PERMS = {
    "allowed": ["summary", "search", "stats", "chat", "help"],
    "admin_enabled": False,
    "admin_public": False,
    "auto_reply": True,
}
ALL_COMMANDS = ["summary", "search", "stats", "chat", "help", "persona", "knowledge", "admin"]
