"""QQ Bot 入口 — 加载配置、初始化、启动主循环"""
import asyncio
import os
import subprocess
import sys

from .config import (API_KEY, ACTIVE_PERSONA_FILE, DB_PATH, ADMIN_QQ)
from .db import init_db, db_stats
from .state import (silenced_groups, active_persona)
from .send import load_json, load_personas, load_auto_reply_rules, load_silenced
from .handlers.dispatch import connect_ws
from .handlers.health import revive_checker, connection_health_checker


def _kill_old_bridges():
    """防重：kill 旧桥接 python 进程（只匹配 python，避免误杀父 shell）"""
    result = subprocess.run(
        ["pgrep", "-f", "python.*qq_bot"], capture_output=True, text=True)
    my_pid = os.getpid()
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        try:
            pid = int(line.strip())
            if pid != my_pid:
                try:
                    os.kill(pid, 9)
                    print(f"[启动] 已杀死旧桥接进程 PID={pid}")
                except Exception as e:
                    print(f"[启动] 无法杀死旧进程 PID={pid}: {e}")
        except ValueError:
            pass


async def main():
    _kill_old_bridges()

    if API_KEY == "your-api-key-here":
        print("[错误] 请先设置 DEEPSEEK_API_KEY")
        sys.exit(1)

    init_db()
    personas = load_personas()
    rules = load_auto_reply_rules()
    global silenced_groups
    silenced_groups.update(load_silenced())

    saved_active = load_json(ACTIVE_PERSONA_FILE, {})
    for k, v in saved_active.items():
        try:
            active_persona[int(k)] = v
        except ValueError:
            pass

    print("=" * 50)
    print("  QQ 群聊智能机器人 v5.0 (modular)")
    print(f"  管理员: {[q for q in ADMIN_QQ if q]}")
    print(f"  人设: {len(personas)} 个 | 自动回复规则: {len(rules)} 条")
    print(f"  活跃人设: {active_persona}")
    print(f"  {db_stats()}")
    print("=" * 50)

    while True:
        try:
            await asyncio.gather(
                connect_ws(),
                revive_checker(),
                connection_health_checker(),
            )
        except Exception as e:
            print(f"[致命] 主循环异常: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc(file=sys.stderr)
            await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
