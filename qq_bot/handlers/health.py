"""假死检测 / 冷群复活 / 自动重启"""
import asyncio
import subprocess
import sys
from datetime import datetime

from ..config import (REVIVE_CHECK_INTERVAL, REVIVE_DAY_START, REVIVE_DAY_END,
                       REVIVE_SILENCE_MINUTES, REVIVE_EXCLUDE_GROUPS,
                       HEALTH_CHECK_INTERVAL, HEALTH_CHECK_MAX_FAILURES,
                       HEALTH_SILENCE_WARN_MINUTES, RESTART_COOLDOWN,
                       QQ_PROCESS_PATTERN, QQ_RESTART_CMD, QQ_ACCOUNT, ADMIN_QQ)
from ..state import (last_msg_time, silenced_groups, _ws, _health_check_failures,
                      _last_restart_time, _kicked_offline_detected)
from ..permissions import get_persona_for_group
from ..send import send_group_msg, send_private_msg, maybe_sticker
from ..llm import call_llm, safe_system_prompt


async def revive_checker():
    while _ws is None:
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
                    await send_group_msg(_ws, group_id, maybe_sticker(reply, group_id))
                    print(f"[复活] 群{group_id} 沉默{silence:.0f}分钟，已发送")
                last_msg_time[group_id] = now


async def connection_health_checker():
    global _health_check_failures
    from ..ws import call_api

    while _ws is None:
        await asyncio.sleep(5)

    print(f"[健康检查] 已启动（每{HEALTH_CHECK_INTERVAL}s API探测，连续{HEALTH_CHECK_MAX_FAILURES}次失败触发重启）")

    while True:
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)
        if _ws is None:
            continue
        if _kicked_offline_detected:
            print("[健康检查] 检测到 KickedOffLine 标记，触发重启...")
            await _restart_napcat()
            continue

        healthy = False
        for attempt in range(2):
            result = await call_api("send_private_msg",
                {"user_id": int(QQ_ACCOUNT), "message": "."}, timeout=15)
            if result and result.get("status") == "ok":
                healthy = True
                break
            await asyncio.sleep(5)

        if healthy and last_msg_time:
            most_recent = max(last_msg_time.values()) if last_msg_time else None
            if most_recent:
                silence_minutes = (datetime.now() - most_recent).total_seconds() / 60
                if silence_minutes > HEALTH_SILENCE_WARN_MINUTES:
                    print(f"[健康检查] 所有群已沉默 {silence_minutes:.0f} 分钟（仅提示，API正常）")

        if healthy:
            if _health_check_failures > 0:
                print(f"[健康检查] 已恢复（之前失败 {_health_check_failures} 次）")
            _health_check_failures = 0
            continue

        _health_check_failures += 1
        proc_alive = False
        try:
            p = subprocess.run(["pgrep", "-f", QQ_PROCESS_PATTERN], capture_output=True, timeout=5)
            proc_alive = bool(p.stdout.strip())
        except Exception:
            pass
        status = "QQ进程存活但API无响应，可能被踢" if proc_alive else "QQ进程已死亡"
        print(f"[健康检查] API 探测失败 ({_health_check_failures}/{HEALTH_CHECK_MAX_FAILURES}) - {status}")

        if _health_check_failures >= HEALTH_CHECK_MAX_FAILURES:
            print("[健康检查] 连续探测失败，判定连接假死，触发重启...")
            await _restart_napcat()


async def _restart_napcat():
    global _last_restart_time, _health_check_failures, _kicked_offline_detected
    now = datetime.now()

    if _last_restart_time and (now - _last_restart_time).total_seconds() < RESTART_COOLDOWN:
        cooldown_left = RESTART_COOLDOWN - (now - _last_restart_time).total_seconds()
        print(f"[重启] 冷却中，{cooldown_left:.0f}s 后才能再次重启")
        return

    _last_restart_time = now
    _health_check_failures = 0
    _kicked_offline_detected = False

    print("[重启] 正在重启 NapCat QQ 进程...")
    try:
        proc = await asyncio.create_subprocess_exec(
            "pkill", "-f", QQ_PROCESS_PATTERN,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await proc.wait()
        print("[重启] 已杀掉旧 QQ 进程")
        await asyncio.sleep(5)
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", QQ_RESTART_CMD,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.wait_for(proc.wait(), timeout=10)
        print("[重启] QQ 进程已重新启动")
        await asyncio.sleep(25)

        if _ws:
            for admin in ADMIN_QQ:
                try:
                    await send_private_msg(_ws, admin,
                        f"[Bot自动重启通知]\n时间: {now.strftime('%m-%d %H:%M:%S')}\n"
                        f"原因: 检测到假死/被踢下线\nNapCat 已自动重启，桥接将自动重连...")
                except Exception:
                    pass
            try:
                await _ws.close()
            except Exception:
                pass
    except Exception as e:
        print(f"[重启] 失败: {e}")
        import traceback
        traceback.print_exc()
