"""冷群复活"""
import asyncio
from datetime import datetime

from ..config import (REVIVE_CHECK_INTERVAL, REVIVE_DAY_START, REVIVE_DAY_END,
                       REVIVE_SILENCE_MINUTES, REVIVE_EXCLUDE_GROUPS)
from .. import state as bot_state
from ..state import last_msg_time, silenced_groups
from ..permissions import get_persona_for_group
from ..send import send_group_msg, maybe_sticker
from ..llm import call_llm, safe_system_prompt


async def revive_checker():
    while bot_state._ws is None:
        await asyncio.sleep(5)

    print(f"[复活] 冷群检查已启动（白天{REVIVE_DAY_START}:00-{REVIVE_DAY_END}:00，"
          f"沉默{REVIVE_SILENCE_MINUTES}分钟触发，排除群{REVIVE_EXCLUDE_GROUPS}）")

    while True:
        await asyncio.sleep(REVIVE_CHECK_INTERVAL)
        now = datetime.now()
        if now.hour < REVIVE_DAY_START or now.hour >= REVIVE_DAY_END:
            continue

        for group_id, last_time in list(last_msg_time.items()):
            if group_id in REVIVE_EXCLUDE_GROUPS or group_id in silenced_groups:
                continue
            silence = (now - last_time).total_seconds() / 60
            if silence >= REVIVE_SILENCE_MINUTES:
                person = get_persona_for_group(group_id)
                reply = await call_llm([
                    {"role": "system", "content": f"{safe_system_prompt(person)} 群已经沉默了{silence:.0f}分钟，你是群里的成员。请自然地打破沉默，比如问大家在忙什么、分享一个有趣的话题等。要贴合你当前的人设。"},
                    {"role": "user", "content": "群里好一阵没人说话了，你发点什么活跃一下气氛吧。"},
                ], max_tokens=120, temperature=0.9)
                if reply:
                    await send_group_msg(bot_state._ws, group_id, maybe_sticker(reply, group_id))
                    print(f"[复活] 群{group_id} 沉默{silence:.0f}分钟，已发送")
                last_msg_time[group_id] = now


        import traceback
        traceback.print_exc()
