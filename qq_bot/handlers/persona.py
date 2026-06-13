"""人设管理命令处理"""
import re

from ..state import active_persona, conv_history
from ..permissions import save_active_personas
from ..send import send_group_msg, load_personas, save_personas
from ..llm import call_llm


async def handle_persona(ws, group_id, user_id, cmd):
    personas = load_personas()

    # === 新建人设 ===
    m = re.search(r"创建人设\s*(\S+)", cmd)
    if m:
        new_key = m.group(1).strip()
        if new_key in personas:
            await send_group_msg(ws, group_id, f"「{new_key}」已存在。用 @bot 修改人设 来改它。")
            return
        desc = re.sub(r"创建人设\s*\S+\s*", "", cmd).strip()
        if not desc:
            await send_group_msg(ws, group_id,
                "格式：@bot 创建人设 <英文key> <描述>\n"
                "例如：@bot 创建人设 tsundere 傲娇猫娘，说话带喵，口嫌体正直")
            return
        await send_group_msg(ws, group_id, f"正在用 LLM 生成人设「{new_key}」...")
        new_prompt = await call_llm([
            {"role": "system", "content": (
                "你是人设生成器。根据描述生成一个 system_prompt，让 AI 扮演该角色。\n"
                "格式：先给角色起一个中文名，然后描述性格、口癖、回复风格。150 字以内。"
            )},
            {"role": "user", "content": f"人设 key: {new_key}\n描述: {desc}"},
        ], max_tokens=300, temperature=0.8)
        if new_prompt:
            personas[new_key] = {"name": new_key, "system_prompt": new_prompt.strip()}
            save_personas(personas)
            await send_group_msg(ws, group_id, f"人设「{new_key}」已创建 ✓ 用 @bot 切换 {new_key} 来启用")
        else:
            await send_group_msg(ws, group_id, "创建失败，请稍后重试。")
        return

    # === 切换人设 ===
    m = re.search(r"切换\s*(\S+)", cmd)
    if m:
        name = m.group(1)
        if name in personas:
            active_persona[group_id] = name
            save_active_personas()
            for k in list(conv_history):
                if k[0] == group_id:
                    del conv_history[k]
            p = personas[name]
            await send_group_msg(ws, group_id, f"已切换为人设「{p['name']}」")
            return
        if name != "人设":
            names = " / ".join(personas.keys())
            await send_group_msg(ws, group_id, f"没有「{name}」这个人设。可用：{names}")
            return

    # === 循环切换人设 ===
    if re.search(r"^切换$|^切换人设$", cmd):
        names = list(personas.keys())
        if len(names) <= 1:
            await send_group_msg(ws, group_id, "只有一个人设，无法切换。用 @bot 创建人设 来新建。")
            return
        current = active_persona.get(group_id, "default")
        idx = names.index(current) if current in names else 0
        next_name = names[(idx + 1) % len(names)]
        active_persona[group_id] = next_name
        save_active_personas()
        for k in list(conv_history):
            if k[0] == group_id:
                del conv_history[k]
        p = personas[next_name]
        await send_group_msg(ws, group_id, f"已切换为人设「{p['name']}」")
        return

    # === 修改人设 ===
    if re.search(r"修改", cmd):
        current = active_persona.get(group_id, "default")
        p = personas.get(current, personas["default"])
        desc = re.sub(r"修改人设|修改", "", cmd, count=1).strip()
        if not desc:
            await send_group_msg(ws, group_id,
                f"当前人设「{p['name']}」。请描述你想怎么改，例如：\n"
                f"@bot 修改人设 让她说话更温柔一点，不要那么傲娇")
            return
        await send_group_msg(ws, group_id, f"正在修改人设「{p['name']}」...")
        new_prompt = await call_llm([
            {"role": "system", "content": (
                "你是一个人设编辑器。根据用户的要求修改下面的 system_prompt。\n"
                "规则：\n"
                "1. 保持原有的角色名(name)和背景设定不变，只按用户要求调整性格、口癖、回复风格\n"
                "2. 只输出修改后的完整 system_prompt，不要加任何解释或前缀\n"
                "3. 保持原有格式和长度"
            )},
            {"role": "user", "content": f"当前人设 ({current}):\n{p['system_prompt']}\n\n修改要求: {desc}"},
        ], max_tokens=600, temperature=0.7)
        if new_prompt:
            p["system_prompt"] = new_prompt.strip()
            personas[current] = p
            save_personas(personas)
            await send_group_msg(ws, group_id, f"「{p['name']}」人设已更新 ✓")
        else:
            await send_group_msg(ws, group_id, "修改失败，请稍后重试。")
        return

    # === 人设列表 ===
    if re.search(r"列表", cmd):
        lines = ["🎭 可用人设："]
        for name, p in personas.items():
            active = " ✓" if active_persona.get(group_id, "default") == name else ""
            lines.append(f"  • {name} — {p.get('name', name)}{active}")
        if len(personas) == 1:
            lines.append("\n💡 用 @bot 创建人设 来添加新人设")
        await send_group_msg(ws, group_id, "\n".join(lines))
        return

    # === 人设详情 ===
    if re.search(r"详情", cmd):
        current = active_persona.get(group_id, "default")
        m = re.search(r"详情\s*(\S+)", cmd)
        target = m.group(1) if m else current
        p = personas.get(target)
        if p:
            await send_group_msg(ws, group_id, f"🎭 {target} ({p.get('name', target)})\n{p.get('system_prompt', '无描述')}")
        else:
            await send_group_msg(ws, group_id, "没有这个人设")
        return

    # === 默认：显示当前人设 ===
    current = active_persona.get(group_id, "default")
    p = personas.get(current, personas["default"])
    await send_group_msg(ws, group_id,
        f"当前人设：{current}（{p.get('name', current)}）\n"
        f"可用：@bot 切换 XX / 人设列表 / 人设详情 XX / 创建人设 / 修改人设")
