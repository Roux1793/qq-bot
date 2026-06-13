"""QQ Bot 全局运行时状态"""
from collections import deque
from datetime import datetime

# === 总结冷却 ===
last_summary: dict[int, datetime] = {}

# === 消息计数与缓冲 ===
msg_counter: dict[int, int] = {}
msg_buffer: dict[int, deque] = {}

# === 自动插话冷却 ===
last_auto_chime: dict[int, datetime] = {}
last_auto_reply: dict[int, datetime] = {}
last_quick_chime: dict[int, datetime] = {}

# === 禁言集合 ===
silenced_groups: set[int] = set()

# === 私密总结状态 ===
priv_summary_state: dict[int, dict] = {}  # user_id -> {"group_id": int, "waiting_for_count": bool}

# === WebSocket 连接 ===
_echo_counter = 0
_pending: dict[str, "asyncio.Future"] = {}
_ws: "websockets.WebSocketClientProtocol | None" = None

# === 假死检测 ===
_health_check_failures = 0
_last_restart_time: datetime | None = None
_kicked_offline_detected = False

# === 活跃人设 ===
active_persona: dict[int, str] = {}  # group_id -> persona_name

# === 冷群复活 ===
last_msg_time: dict[int, datetime] = {}

# === 对话记忆 ===
conv_history: dict[tuple[int, int], deque] = {}  # (group_id, user_id) -> deque
