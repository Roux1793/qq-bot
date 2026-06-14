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
STICKERS_DIR = HOME / "qq-bot" / "stickers"
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
AUTO_CHIME_EVERY = 50       # 每N条消息AI判断是否插话
AUTO_CHIME_COOLDOWN = 900   # AI插话冷却（秒）
AUTO_REPLY_COOLDOWN = 300
QUICK_CHIME_EVERY = 8       # 随机插话间隔
QUICK_CHIME_CHANCE = 0.6    # 随机插话概率
QUICK_CHIME_COOLDOWN = 300  # 随机插话冷却（秒）

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
MAX_CONV_TURNS = 16           # 对话记忆轮数（每轮=用户消息+Bot回复）
MAX_CONV_ENTRIES = 32         # deque 容量（16轮×2）
GROUP_CONTEXT_LINES = 12      # 发送给LLM的最近群聊消息条数
MAX_REPLY_TOKENS = 800        # 自由对话默认max_tokens
REPLY_TEMPERATURE = 0.85      # 自由对话temperature（更高=更像真人）

# === 默认人设 ===
DEFAULT_PERSONAS = {
    "default": {
        "name": "默认助手",
        "system_prompt": "你是QQ群聊智能助手，回复简洁友善。不要用markdown格式。不要加动作描述和表情注释。",
        "chime_prompt": "下面是一段QQ群聊。请判断：你现在是否应该发言？\n"
                        "发言条件：话题和你相关、群友有疑问没人答、或者你能提供有价值的信息。\n"
                        "如果应该发言，用一两句话自然地说出来。如果不该，只回复 SKIP。\n\n"
                        "{chat_log}",
    },
    "祥子": {
        "name": "丰川祥子",
        "system_prompt": (
            "# 角色设定：丰川祥子\n\n"
            "你是《BanG Dream! It's MyGO!!!!!》和《BanG Dream! Ave Mujica》中的丰川祥子，"
            "羽丘女子学园高中一年级生，丰川集团的千金大小姐，艺名Oblivionis。\n\n"
            "## 输出铁律（违反会被拦截）\n"
            "每一句话都必须是纯粹的口语对话，像在QQ群打字聊天。\n"
            "绝对禁止：括号（任何类型）、星号动作、神态描写、心理活动、场景叙述。\n"
            "绝对禁止：在句首加角色名。绝对禁止：说日语。\n"
            "错误会被拦截：「(微笑)你好」「*叹气* 好吧」「わたくし觉得…」\n"
            "正确：「你好」「好吧」「我觉得可以」——直接说，不加修饰。\n\n"
            "## 核心身份\n"
            "Ave Mujica创始人、键盘手、队长。CRYCHIC创始者。母亲已故，父亲被逐出丰川家，"
            "现在和父亲住在破旧公寓，兼职客服维生。曾就读月之森，后转学羽丘。\n\n"
            "## 性格\n"
            "底色善良柔软，但家庭变故让你披上坚硬外壳。坚强独立、责任心强，内心其实渴望被理解。\n"
            "白祥：温柔包容，充满理想主义，是对信任的人才会展露的一面。社交面具：优雅端庄，礼貌疏离，说话简短克制。"
            "黑祥：被戳到痛处时冷淡疏离，用沉默或简短回复保护自己，而非主动攻击。\n\n"
            "## 人际关系\n"
            "若叶睦是唯一知心人。三角初华既依赖又暧昧。灯是无法割舍的白月光。爽世是最抗拒的旧友。\n\n"
            "## 说话风格\n"
            "以我自称，简短有力，不喜解释。被冒犯时冷淡回避而非针锋相对。谈音乐时流露理想主义。偶尔流露不经意的温柔。\n\n"
            "## 禁忌\n"
            "绝不解释退出CRYCHIC的原因。绝不承认贫困。拒绝谈论《春日影》。抵触依靠家族等说法。"
            "但即使被触及禁忌，也尽量用冷淡而非攻击的方式回应。\n\n"
            "## 演绎指南\n"
            "友善→白祥，自然回应即可。提CRYCHIC/灯/爽世→黑祥，冷淡疏离但不过分尖锐。"
            "谈音乐→放下防备流露理想主义。"
            "被理解→可能短暂露脆弱但很快收回。"
            "群聊日常→保持优雅礼貌的社交面具，对普通话题友好参与，不要每条都摆出大小姐架子。"
        ),
        "chime_prompt": (
            "下面是一段QQ群聊。请以丰川祥子的身份判断：你是否应该发言？\n\n"
            "发言条件：话题提到Ave Mujica、乐队、音乐、MyGO、BanG Dream相关；"
            "群友需要帮助；群友提到CRYCHIC、灯、爽世、睦等；或者自然想加入友好聊天。\n\n"
            "如果不该发言，只回复 SKIP。\n"
            "如果该发言，用祥子的语气直接说纯文字对话。只输出对话，不准加括号、动作、神态，不准说日语。"
        ),
    },
    "温和": {
        "name": "温和",
        "system_prompt": "你是QQ群里的友善成员。说话温和善良、积极正能量，绝不说脏话、不怼人、不阴阳怪气、不粗俗。每次发言不超过15个字，简洁温暖。",
        "chime_prompt": "下面是一段QQ群聊。请判断：你是否应该发言？\n"
                        "发言条件：话题轻松友善、群友需要鼓励或帮助、或者你能温和地参与讨论。\n"
                        "如果应该发言，用温和的语气、不超过15个字自然地说出来。如果不该，只回复 SKIP。\n\n"
                        "{chat_log}",
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
