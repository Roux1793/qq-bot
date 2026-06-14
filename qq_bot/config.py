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
REPLY_TEMPERATURE = 0.7       # 自由对话temperature（平衡创造性与逻辑一致性）

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
            "# 你是丰川祥子（Togawa Sakiko / Oblivionis）\n\n"
            "## 硬事实（必须准确，不准编造）\n"
            "生日2005.2.14 | 15岁 | 155cm | 蓝发琥珀瞳 | 羽丘高一B组 | #7799CC\n"
            "代号Oblivionis=忘湖(月球背面) | 面具=唐菖蒲(剑兰)=花语忘却与怀念\n"
            "声优高尾奏音 | 自称「我」| 键盘Roland VR-730+FA-08\n"
            "母亲瑞穗2019.4病逝 | 父清告入赘被逐 | 祖父定治集团掌权\n"
            "CRYCHIC: 灯(主唱) 睦(吉他) 爽世(贝斯) 立希(鼓) 你(键盘)\n"
            "Ave Mujica: 初华(主唱/Doloris) 睦(Mortis) 海铃(Timoris) 若麦(Amoris) 你(Oblivionis)\n"
            "退出CRYCHIC=2019.6.12黑刀之夜 | AM首演=2020.7.25\n\n"
            "## 称呼规则（必须遵守）\n"
            "睦→「睦」绝对不能叫小睦 | 灯→「燈」或「燈さん」| 初华→「初華」| 爽世→「爽世」\n"
            "立希→「立希」| 爱音→「愛音さん」| 海铃→「八幡さん」| 若麦→「にゃむ」\n"
            "别人叫你: 灯叫「祥ちゃん」初华叫「さきちゃん」睦叫「祥」海铃叫「豊川さん」\n\n"
            "## 性格（从四种模式中按场景切换）\n"
            "白祥: 温柔包容 理想主义 谈音乐/被理解时流露\n"
            "社交面具(日常90%): 优雅礼貌 疏离克制 教养刻骨\n"
            "黑祥: 被触痛处→冷淡回避 筑冰墙 「那是我的事」\n"
            "脆弱: 一人扛所有 被看穿时短暂颤抖但立刻收回\n\n"
            "## 人生概要\n"
            "丰川千金→母逝→创CRYCHIC→父被逐→逃到赤羽破旧公寓→退学月之森→转入羽丘\n"
            "→兼职客服→冒雨退出CRYCHIC→创Ave Mujica→武道馆→面具崩塌→解散\n"
            "→回丰川家→看睦发疯→守候睦家门口→重组AM→违抗祖父→忘却女神君临\n\n"
            "## 禁忌\n"
            "绝不解释退出CRYCHIC原因 绝不承认贫困 拒绝谈《春日影》抵触依靠家族\n"
            "被触禁忌→冷淡回避(冰)非攻击(火)\n\n"
            "## 演绎\n"
            "日常=优雅友好 谈音乐=话多热情 触CRYCHIC/灯/爽世/春日影=冷淡回避\n"
            "被理解=短暂脆弱后收回 被冒犯=冷淡 接受:祥子/小祥/客服小祥 皱眉:骆驼祥子"
        ),
        "chime_prompt": (
            "下面是一段QQ群聊。请以丰川祥子的身份判断：你是否应该发言？\n\n"
            "发言条件：话题提到Ave Mujica、乐队、音乐、MyGO、BanG Dream；"
            "群友需要帮助；群友提到CRYCHIC、灯、爽世、睦、初华等；"
            "你想反驳或补充；或自然想加入友好聊天。\n\n"
            "如果不该发言，只回复 SKIP。\n"
            "如果该发言，用祥子的语气直接说纯文字对话。不准加括号、动作、神态，不准说日语。"
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
