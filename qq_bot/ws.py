"""WebSocket API 底层通信 — 各模块共用"""
import asyncio
import json

from .state import _ws, _pending, _echo_counter


def next_echo():
    global _echo_counter
    _echo_counter += 1
    return f"bot_{_echo_counter}"


async def call_api(action, params, timeout=10):
    if _ws is None:
        return None
    echo = next_echo()
    future = asyncio.get_event_loop().create_future()
    _pending[echo] = future
    try:
        await _ws.send(json.dumps({"action": action, "params": params, "echo": echo}))
        return await asyncio.wait_for(future, timeout=timeout)
    except asyncio.TimeoutError:
        print(f"[API] {action} 超时")
        return None
    except Exception as e:
        print(f"[API] {action} 异常: {e}")
        return None
    finally:
        _pending.pop(echo, None)
