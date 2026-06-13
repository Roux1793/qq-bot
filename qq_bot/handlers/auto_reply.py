"""自动插话 / 关键词回复 / 冷群复活"""
import random
from collections import deque
from datetime import datetime, timedelta

from ..config import (AUTO_CHIME_EVERY, AUTO_CHIME_COOLDOWN, AUTO_REPLY_COOLDOWN,
                       QUICK_CHIME_EVERY, QUICK_CHIME_CHANCE, QUICK_CHIME_COOLDOWN)
from ..state import (msg_counter, msg_buffer, last_auto_chime, last_auto_reply,
                      last_quick_chime, silenced_groups, last_msg_time)
from ..permissions import group_auto_reply_enabled, get_persona_for_group, is_admin
from ..send import send_group_msg, send_private_msg, maybe_sticker
from ..send import load_auto_reply_rules, save_silenced as do_save_silenced
from ..llm import call_llm


def match_auto_reply(text):
    rules = load_auto_reply_rules()
    for rule in rules:
        kw = rule.get("keyword", "")
        if kw and kw in text:
            return kw, rule.get("hint", "")
    return None, None


async def process_auto_reply(ws, group_id, user_id, nickname, raw_msg, now):
    try:
        await _process_auto_reply(ws, group_id, user_id, nickname, raw_msg, now)
    except Exception as e:
        print(f"[错误] 自动插话异常 (群{group_id}): {e}")


async def _process_auto_reply(ws, group_id, user_id, nickname, raw_msg, now):
    if group_id in silenced_groups:
        return
    if not group_auto_reply_enabled(group_id):
        return

    # 1. 关键词触发
    kw, hint = match_auto_reply(raw_msg)
    if kw:
        if group_id in last_auto_reply:
            if (now - last_auto_reply[group_id]) < timedelta(seconds=AUTO_REPLY_COOLDOWN):
                return
        last_auto_reply[group_id] = now

        persona = get_persona_for_group(group_id)
        buf = list(msg_buffer.get(group_id, deque(maxlen=30)))
        context = "\n".join(buf[-10:])

        time_info = ""
        if kw in ("几点", "时间", "几号", "星期几", "日期"):
            time_info = f"\n当前真实时间：{now.strftime('%Y年%m月%d日 %H:%M，星期%w').replace('星期0', '星期日').replace('星期1', '星期一').replace('星期2', '星期二').replace('星期3', '星期三').replace('星期4', '星期四').replace('星期5', '星期五').replace('星期6', '星期六')}"

        if kw in ("好无聊", "没事干"):
            check = await call_llm([
                {"role": "system", "content": "判断以下群聊消息中，说话者是否真的在表达无聊/没事做想找点事干，还是只是在提到这些词（比如转发、引用、开玩笑）。只回复 YES 或 NO。"},
                {"role": "user", "content": f"消息：{raw_msg}\n上下文：{context}"},
            ], max_tokens=3, temperature=0)
            if not check or "NO" in check.upper():
                return
            reply = await call_llm([
                {"role": "system", "content": f"{persona['system_prompt']} 有人喊无聊了！请用一句话（≤30字）推荐一件事或开一个话题。要贴合你的人设。"},
                {"role": "user", "content": "有人无聊，你简短地回一句"},
            ], max_tokens=80, temperature=0.9)
            if reply:
                await send_group_msg(ws, group_id, maybe_sticker(reply))
                print(f"[群{group_id}] 自动回复: 触发「{kw}」(已核实)")
            return

        reply = await call_llm([
            {"role": "system", "content": f"{persona['system_prompt']} 当前群聊中提到了「{kw}」，请自然地加入对话。要求：{hint}。用口语化中文，简短自然。"},
            {"role": "user", "content": f"群聊上下文：\n{context}{time_info}\n\n请你自然地插一句："},
        ], max_tokens=200, temperature=0.8)

        if reply:
            await send_group_msg(ws, group_id, maybe_sticker(reply))
            print(f"[群{group_id}] 自动回复: 触发「{kw}」")
        return

    # 2. AI 自主插话
    if group_id not in msg_counter:
        msg_counter[group_id] = 0
    msg_counter[group_id] += 1

    if msg_counter[group_id] % AUTO_CHIME_EVERY == 0:
        if group_id in last_auto_chime:
            if (now - last_auto_chime[group_id]) < timedelta(seconds=AUTO_CHIME_COOLDOWN):
                return
        last_auto_chime[group_id] = now
        chime = await _ai_should_chime(group_id)
        if chime:
            await send_group_msg(ws, group_id, maybe_sticker(chime))
            print(f"[群{group_id}] AI自主插话")

    # 3. 随机插话
    if msg_counter[group_id] % QUICK_CHIME_EVERY == 0:
        if random.random() >= QUICK_CHIME_CHANCE:
            return
        if group_id in last_quick_chime:
            if (now - last_quick_chime[group_id]) < timedelta(seconds=QUICK_CHIME_COOLDOWN):
                return
        last_quick_chime[group_id] = now

        persona = get_persona_for_group(group_id)
        buf = list(msg_buffer.get(group_id, deque(maxlen=30)))
        if len(buf) < 10:
            return
        chat_log = "\n".join(buf[-10:])

        quick_reply = await call_llm([
            {"role": "system", "content": persona["system_prompt"]},
            {"role": "user", "content": f"下面是最新的QQ群聊。请根据当前话题自然地插一句话（≤30字），要贴合群聊氛围。不用管别人是否@你。\n\n{chat_log}"},
        ], max_tokens=80, temperature=1.0)
        if quick_reply:
            await send_group_msg(ws, group_id, maybe_sticker(quick_reply))
            print(f"[群{group_id}] 随机插话")


async def _ai_should_chime(group_id):
    persona = get_persona_for_group(group_id)
    buf = list(msg_buffer.get(group_id, deque(maxlen=50)))
    if len(buf) < 10:
        return None
    chat_log = "\n".join(buf[-30:])
    from ..config import DEFAULT_PERSONAS
    prompt = persona.get("chime_prompt", DEFAULT_PERSONAS["default"]["chime_prompt"]).format(chat_log=chat_log)
    result = await call_llm([
        {"role": "system", "content": persona["system_prompt"]},
        {"role": "user", "content": prompt},
    ], max_tokens=120, temperature=0.7)
    if result and "SKIP" not in result.upper():
        return result.strip()
    return None
