"""QQ Bot 权限管理 + 人设获取 + 管理员检查"""
from pathlib import Path
from .config import ADMIN_QQ, PERMS_FILE, DEFAULT_PERMS, ACTIVE_PERSONA_FILE, GROUP_MAX_MSG_LENGTH
from .send import load_json, save_json, load_personas, get_group_style
from .state import active_persona

# 跟踪 JSON 文件的修改时间，避免每次都读盘
_persona_file_mtime: float = 0


def _reload_active_personas_if_changed():
    """如果 active_personas.json 被外部修改（如控制面板），重新加载"""
    global _persona_file_mtime
    try:
        mtime = ACTIVE_PERSONA_FILE.stat().st_mtime
    except OSError:
        return
    if mtime <= _persona_file_mtime:
        return
    _persona_file_mtime = mtime
    data = load_json(ACTIVE_PERSONA_FILE, {})
    # 清除旧数据，写入新数据（用更新而不是替换，避免其他模块持有的引用失效）
    active_persona.clear()
    active_persona.update({int(k): v for k, v in data.items()})


def is_admin(user_id):
    return user_id in ADMIN_QQ


# ====== 群权限 ======

def load_perms() -> dict:
    data = load_json(PERMS_FILE, {"default": DEFAULT_PERMS})
    if "default" not in data:
        data["default"] = DEFAULT_PERMS
    return data


def get_group_perms(group_id: int) -> dict:
    data = load_perms()
    key = str(group_id)
    if key in data:
        return data[key]
    return data.get("default", DEFAULT_PERMS)


def group_has_perm(group_id: int, command: str) -> bool:
    perms = get_group_perms(group_id)
    return command in perms.get("allowed", [])


def group_admin_enabled(group_id: int) -> bool:
    perms = get_group_perms(group_id)
    return perms.get("admin_enabled", False)


def group_admin_public(group_id: int) -> bool:
    perms = get_group_perms(group_id)
    return perms.get("admin_public", False)


def group_auto_reply_enabled(group_id: int) -> bool:
    perms = get_group_perms(group_id)
    return perms.get("auto_reply", True)


# ====== 人设 ======

def save_active_personas():
    save_json(ACTIVE_PERSONA_FILE, {str(k): v for k, v in active_persona.items()})


def get_persona_for_group(group_id):
    _reload_active_personas_if_changed()  # 面板/文件修改后即时生效，无需重启
    personas = load_personas()
    name = active_persona.get(group_id, "default")
    persona = personas.get(name, personas.get("default", {"name": "默认",
        "system_prompt": "你是QQ群聊助手，简洁友好地回复群友。"})).copy()
    style = get_group_style(group_id)
    if style:
        persona["system_prompt"] = (
            persona["system_prompt"] + "\n\n【群聊风格参考——了解群友的正面积交流习惯。注意：不模仿粗俗/辱骂内容】\n" + style
        )
    return persona
