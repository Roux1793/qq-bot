"""WebSocket API 底层通信 — 各模块共用"""
import asyncio
import json

from . import state


def _get_ws():
    return state._ws


async def call_api(action, params, timeout=10):
    """发送 API 请求并直接读 WS 响应，绕过主循环死锁"""
    ws = _get_ws()
    if ws is None:
        return None

    state._echo_counter += 1
    echo = f"bot_{state._echo_counter}"

    try:
        await ws.send(json.dumps({"action": action, "params": params, "echo": echo}))
    except Exception as e:
        print(f"[API] send fail ({action}): {e}")
        return None

    try:
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("echo") == echo:
                return data
            # 其他消息存 backlog，下一轮主循环处理
            from . import state as st
            if not hasattr(st, '_backlog'):
                st._backlog = []
            st._backlog.append(raw)
    except asyncio.TimeoutError:
        print(f"[API] {action} timeout")
        return None
    except Exception as e:
        print(f"[API] {action} error: {e}")
        return None
