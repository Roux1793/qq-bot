"""核心消息分发 + WebSocket 连接管理"""
import asyncio
import json
import os
import re
import sys
from collections import deque
from datetime import datetime, timedelta

import httpx
import websockets

from ..config import (WS_URL, ADMIN_QQ, STYLE_UPDATE_INTERVAL,
                       MAX_CONV_ENTRIES, REPLY_TEMPERATURE)
from .. import state as bot_state
from ..state import (msg_buffer, last_msg_time,
                      silenced_groups, priv_summary_state, conv_history,
                      active_persona, last_summary)
from ..db import init_db, save_message, cleanup_old_messages, db_stats
from ..permissions import (is_admin, group_has_perm, group_admin_enabled,
                            group_admin_public, save_active_personas)
from ..send import (send_group_msg, send_private_msg, maybe_sticker,
                     load_json, load_personas, load_auto_reply_rules,
                     load_silenced, save_silenced)
from ..llm import call_llm, HELP_TEXT, ADMIN_HELP, update_group_style
from ..fetch import fetch_messages
from ..llm import generate_summary

from .summary import handle_summary
from .search import handle_search
from .stats import handle_stats
from .persona import handle_persona
from .admin import handle_admin, handle_knowledge, _extract_knowledge
from .auto_reply import process_auto_reply
from ..ws import call_api
from .conversation import build_conversation


# ====== 引用解析 ======

async def _resolve_reply(group_id: int, reply_id: int) -> dict | None:
    """通过 HTTP API 精确查找被引用的消息（HTTP 无死锁问题）"""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.post(
                "http://127.0.0.1:3000/get_msg",
                json={"message_id": reply_id})
        if r.status_code == 200:
            data = r.json()
            if data.get("status") == "ok":
                msg = data.get("data", {})
                sender = msg.get("sender", {})
                nick = sender.get("card") or sender.get("nickname") or "?"
                content = msg.get("raw_message") or msg.get("message", "")
                if isinstance(content, list):
                    parts = []
                    for seg in content:
                        if seg.get("type") == "text":
                            parts.append(seg.get("data", {}).get("text", ""))
                    content = "".join(parts)
                content = str(content).strip()
                if content:
                    from ..config import QQ_ACCOUNT
                    is_bot = str(msg.get("user_id", 0)) == str(QQ_ACCOUNT)
                    return {
                        "text": f"「{nick}」说过：{content[:200]}",
                        "is_bot": is_bot,
                        "content": content[:300],
                    }
    except Exception as e:
        print(f"[引用] HTTP 查找失败: {e}")
    return None



# ====== WebSocket 连接 ======

async def connect_ws():
    retry = 0
    was_previously_connected = False
    while True:
        try:
            print(f"[WS] 连接 {WS_URL} ...")
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10, max_size=2**23) as ws:
                bot_state._ws = ws
                print("[WS] 已连接")
                retry = 0
                if was_previously_connected and ADMIN_QQ:
                    print("[WS] 断开重连成功，通知管理员...")
                    for admin in ADMIN_QQ:
                        await send_private_msg(ws, admin,
                            f"[Bot重连通知]\n时间: {datetime.now().strftime('%m-%d %H:%M:%S')}\nWS已重新连接到NapCat")
                    was_previously_connected = False
                await handle_messages(ws)
        except (websockets.ConnectionClosed, OSError) as e:
            if bot_state._ws is not None:
                was_previously_connected = True
            bot_state._ws = None
            retry += 1
            delay = min(retry * 5, 60)
            print(f"[WS] 断开: {e}，{delay}s 后重连")
            await asyncio.sleep(delay)


# ====== 指令路由：功能性（不加载人设）======

async def _try_functional(ws, group_id, user_id, cmd, effective_admin, now) -> bool:
    """处理功能性指令。返回 True 表示已处理，False 表示不是功能性指令。"""
    perms_ok = group_has_perm

    # ── help ──
    if re.search(r"help|帮助|命令|功能", cmd):
        if not perms_ok(group_id, "help"):
            await send_group_msg(ws, group_id, "此群未开启 help 功能。")
            return True
        await send_group_msg(ws, group_id,
            HELP_TEXT + ("\n\n" + ADMIN_HELP if effective_admin else ""))
        return True

    # ── 搜索 ──
    if re.search(r"搜索|查找|搜", cmd):
        if not perms_ok(group_id, "search"):
            await send_group_msg(ws, group_id, "此群未开启搜索功能。")
            return True
        await handle_search(ws, group_id, cmd)
        return True

    # ── 统计（仅以"统计"/"排行"/"活跃"开头才触发）──
    if re.match(r"统计|排行|活跃", cmd):
        if not perms_ok(group_id, "stats"):
            await send_group_msg(ws, group_id, "此群未开启统计功能。")
            return True
        await handle_stats(ws, group_id)
        return True

    # ── 总结（仅以"总结"/"汇总"/"整理"开头才触发）──
    if re.match(r"总结|汇总|整理", cmd):
        if not perms_ok(group_id, "summary"):
            await send_group_msg(ws, group_id, "此群未开启总结功能。")
            return True
        await handle_summary(ws, group_id, user_id, cmd, now)
        return True

    # ── 知识库（只读）──
    if re.search(r"回忆|知识点|知识列表", cmd):
        await handle_knowledge(ws, group_id, cmd)
        return True

    # ── 规则列表（只读）──
    if re.search(r"规则列表|查看规则", cmd):
        await handle_admin(ws, group_id, user_id, cmd)
        return True

    # ── 禁言/恢复 ──
    if re.search(r"^silence$|^静音$|^闭嘴$", cmd):
        if not effective_admin:
            await send_group_msg(ws, group_id, "权限不足。")
        else:
            silenced_groups.add(group_id)
            save_silenced()
            await send_group_msg(ws, group_id, "已静默，不再主动发言。")
            print(f"[禁言] 群{group_id} 已 silence")
        return True

    if re.search(r"^恢复$|^解除$|^说话$", cmd):
        if not effective_admin:
            await send_group_msg(ws, group_id, "权限不足。")
        else:
            silenced_groups.discard(group_id)
            save_silenced()
            await send_group_msg(ws, group_id, "已恢复发言 ✓")
            print(f"[禁言] 群{group_id} 已恢复")
        return True

    # ── 提取知识 / 加删规则 / admin ──
    if re.search(r"提取知识|分析知识|加规则|删规则", cmd) or cmd.startswith("admin"):
        if not effective_admin:
            await send_group_msg(ws, group_id, "权限不足。")
        else:
            await handle_admin(ws, group_id, user_id, cmd)
        return True

    return False


# ====== 指令路由：人设驱动（加载人设 + 对话历史）======

async def _try_persona(ws, group_id, user_id, cmd, effective_admin) -> bool:
    """处理人设相关指令。返回 True 表示已处理。"""
    # ── 人设管理 ──
    if re.search(r"切换|人设|修改人设|创建人设", cmd):
        is_readonly = not re.search(r"切换|修改|创建", cmd)
        if is_readonly:
            await handle_persona(ws, group_id, user_id, cmd)
        elif effective_admin:
            await handle_persona(ws, group_id, user_id, cmd)
        else:
            await send_group_msg(ws, group_id,
                "权限不足。切换/修改/创建人设需要管理员权限。\n"
                "全员可用：@bot 人设列表 / 人设详情 <名称>")
        return True

    return False


# ====== 核心消息处理 ======

async def handle_messages(ws):
    last_cleanup = datetime.now()
    knowledge_extract_counter = 0
    style_update_counter = 0

    async for raw in ws:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        echo = data.get("echo")
        if echo and echo in _pending:
            _pending[echo].set_result(data)
            continue

        # 生命周期事件
        if data.get("post_type") == "meta_event" and data.get("meta_event_type") == "lifecycle":
            sub = data.get("sub_type", "")
            detail = str(data.get("detail", ""))
            if sub in ("offline", "disconnect"):
                reason = detail if detail else sub
                print(f"[状态] QQ 已离线 ({reason})")
                for admin in ADMIN_QQ:
                    await send_private_msg(ws, admin,
                        f"[Bot离线通知]\n时间: {datetime.now().strftime('%m-%d %H:%M:%S')}\n原因: {reason}")
            elif sub in ("connect", "online"):
                print(f"[状态] QQ 已上线 ({sub})")
                for admin in ADMIN_QQ:
                    await send_private_msg(ws, admin,
                        f"[Bot上线通知]\n时间: {datetime.now().strftime('%m-%d %H:%M:%S')}\n状态: 已重新连接")
            continue

        # 忽略离线文件通知
        if data.get("post_type") == "notice" and data.get("notice_type") == "offline_file":
            continue

        # === 私聊消息 ===
        if data.get("post_type") == "message" and data.get("message_type") == "private":
            user_id = data.get("user_id")
            if not is_admin(user_id):
                continue
            raw_msg = data.get("raw_message", "").strip()

            # 私密总结：等待数量回复
            state = priv_summary_state.get(user_id)
            if state and state.get("waiting_for_count"):
                m = re.match(r"(\d+)", raw_msg)
                if m:
                    count = max(10, min(2000, int(m.group(1))))
                    gid = state["group_id"]
                    del priv_summary_state[user_id]
                    await send_private_msg(ws, user_id, f"正在从QQ拉取群 {gid} 最近 {count} 条消息...")
                    lines, source = await fetch_messages(gid, count)
                    if len(lines) < 1:
                        await send_private_msg(ws, user_id, f"群 {gid} 没有找到消息~")
                    else:
                        if source == 'db':
                            await send_private_msg(ws, user_id,
                                f"⚠️ QQ API 不可用，以下为本地缓存的 {len(lines)} 条消息（可能不是最新）")
                        summary = await generate_summary(gid, lines, time_label=f"最近{count}条")
                        if summary:
                            await send_private_msg(ws, user_id,
                                f"📌 群 {gid} 最近 {count} 条消息总结：\n\n{summary}")
                        else:
                            await send_private_msg(ws, user_id, "总结失败，请稍后重试。")
                    continue
                else:
                    await send_private_msg(ws, user_id, "请输入要总结的条数（数字），例如：200")
                    continue

            # silence/恢复
            m = re.match(r"(\d{5,15})\s*(silence|恢复)", raw_msg)
            if m:
                gid = int(m.group(1))
                action = m.group(2)
                if action == "silence":
                    silenced_groups.add(gid)
                    save_silenced()
                    await send_private_msg(ws, user_id, f"群 {gid} 已禁言 ✓")
                    print(f"[禁言] 群{gid} 已 silence (管理员私聊)")
                else:
                    silenced_groups.discard(gid)
                    save_silenced()
                    await send_private_msg(ws, user_id, f"群 {gid} 已恢复 ✓")
                    print(f"[禁言] 群{gid} 已恢复 (管理员私聊)")
                continue

            # 私密切换人设
            m = re.match(r"切换\s*(\d{5,15})", raw_msg)
            if m:
                gid = int(m.group(1))
                personas = load_personas()
                names = list(personas.keys())
                current = active_persona.get(gid, "default")
                idx = names.index(current) if current in names else 0
                next_name = names[(idx + 1) % len(names)]
                active_persona[gid] = next_name
                save_active_personas()
                for k in list(conv_history):
                    if k[0] == gid:
                        del conv_history[k]
                p = personas[next_name]
                await send_private_msg(ws, user_id, f"群 {gid} 已切换为「{p['name']}」✓")
                print(f"[私密切换] 群{gid} 人设 → {next_name}")
                continue

            # 私密统计
            m = re.match(r"统计\s*(\d{5,15})", raw_msg)
            if m:
                gid = int(m.group(1))
                await send_private_msg(ws, user_id, f"正在统计群 {gid} ...")
                from ..fetch import sync_to_db_cached
                from ..db import get_stats
                await sync_to_db_cached(gid)
                stats = get_stats(gid)
                if stats["total"] == 0:
                    await send_private_msg(ws, user_id, f"群 {gid} 暂无聊天数据~")
                else:
                    lines = [f"📊 群 {gid} 统计 | 已收录 {stats['days']} 天，共 {stats['total']} 条", ""]
                    if stats["top_users"]:
                        lines.append("🏆 话痨排行：")
                        medals = ["🥇", "🥈", "🥉"]
                        for i, (uid, name, cnt) in enumerate(stats["top_users"][:10]):
                            prefix = medals[i] if i < 3 else f"{i + 1}."
                            lines.append(f"  {prefix} {name}({uid}): {cnt} 条 ({cnt / stats['total'] * 100:.1f}%)")
                        lines.append("")
                    if stats["hourly"]:
                        peak = max(stats["hourly"], key=lambda x: x[1])
                        dead = min(stats["hourly"], key=lambda x: x[1])
                        lines.append(f"⏰ 最活跃: {peak[0]}:00 ({peak[1]}条) | 最冷清: {dead[0]}:00 ({dead[1]}条)")
                        lines.append("")
                    if len(stats["daily"]) >= 2:
                        recent = stats["daily"][:7]
                        avg = sum(c for _, c in recent) / len(recent)
                        best = max(recent, key=lambda x: x[1])
                        lines.append(f"📅 近7天日均 {avg:.0f} 条 | 最热闹: {best[0]} ({best[1]} 条)")
                    await send_private_msg(ws, user_id, "\n".join(lines))
                    print(f"[私密统计] 管理员查询群{gid}统计 ({stats['total']} 条)")
                continue

            # 总结群号 → 进入私密总结流程
            m = re.match(r"总结\s*(\d{5,15})", raw_msg)
            if m:
                gid = int(m.group(1))
                priv_summary_state[user_id] = {"group_id": gid, "waiting_for_count": True}
                await send_private_msg(ws, user_id, f"要总结群 {gid} 多少条消息？请回复数字（10-2000）：")
                print(f"[私密总结] 管理员请求总结群{gid}")
                continue

            continue

        # === 群聊消息 ===
        if data.get("post_type") != "message" or data.get("message_type") != "group":
            continue

        group_id = data.get("group_id")
        user_id = data.get("user_id")
        raw_msg = data.get("raw_message", "").strip()
        sender = data.get("sender", {})
        nickname = sender.get("card") or sender.get("nickname") or str(user_id)

        if not group_id or not raw_msg:
            continue

        save_message(group_id, user_id, nickname, raw_msg)
        now = datetime.now()
        last_msg_time[group_id] = now

        if group_id not in msg_buffer:
            msg_buffer[group_id] = deque(maxlen=60)
        ts = now.strftime("%H:%M")
        mid = data.get("message_id", 0)
        msg_buffer[group_id].append(f"{mid}|[{ts}] {nickname}: {raw_msg}")

        # 定期清理 & 知识提取 & 风格学习
        if (now - last_cleanup) > timedelta(hours=1):
            cleanup_old_messages()
            last_cleanup = now
        knowledge_extract_counter += 1
        if knowledge_extract_counter % 200 == 0:
            from ..db import query_messages
            if query_messages(group_id, limit=50):
                asyncio.create_task(_extract_knowledge(None, group_id))
        style_update_counter += 1
        if style_update_counter % STYLE_UPDATE_INTERVAL == 0:
            asyncio.create_task(update_group_style(group_id))

        # 检查 @bot
        self_id = data.get("self_id")
        at_pattern = f"[CQ:at,qq={self_id}]"
        is_at_bot = at_pattern in raw_msg if self_id else False

        try:
            if is_at_bot:
                cmd = raw_msg.replace(at_pattern, "").strip()
                print(f"[群{group_id}] {nickname} @bot: {cmd[:60]}")

                if group_id in silenced_groups and not re.search(r"^恢复$|^解除$|^说话$", cmd):
                    continue

                real_admin = is_admin(user_id)
                admin_enabled = group_admin_enabled(group_id)
                admin_public = group_admin_public(group_id)
                effective_admin = real_admin or (admin_enabled and admin_public)

                # ═══════════════════════════════════════════════════════════
                #  功能性指令 — 不加载人设，不记录对话历史，纯工具
                # ═══════════════════════════════════════════════════════════

                if await _try_functional(ws, group_id, user_id, cmd, effective_admin, now):
                    continue

                # ═══════════════════════════════════════════════════════════
                #  人设驱动指令 — 加载人设，记录对话历史，角色扮演
                # ═══════════════════════════════════════════════════════════

                if await _try_persona(ws, group_id, user_id, cmd, effective_admin):
                    continue

                # ── 自由对话（默认人设路径）──
                if not group_has_perm(group_id, "chat"):
                    continue

                # 解析 QQ 引用（reply）— 通过 API 精确查找被引用消息
                reply_context = ""
                reply_to_bot = ""  # 回复 Bot 自己消息时的高优先级上下文
                clean_cmd = cmd
                reply_match = re.match(r"^\[CQ:reply,id=(-?\d+)\]", cmd)
                if reply_match:
                    reply_id = int(reply_match.group(1))
                    clean_cmd = cmd[reply_match.end():].strip()
                    resolved = await _resolve_reply(group_id, reply_id)
                    if resolved:
                        if resolved.get("is_bot"):
                            # 回复的是 Bot 自己的消息 → 最高优先级，强制回顾
                            reply_to_bot = resolved["content"]
                            reply_context = f"（此人在回复你刚才说的「{resolved['content'][:80]}」）"
                        else:
                            reply_context = f"（此人在回复 {resolved['text']}）"
                    elif clean_cmd:
                        reply_context = "（此人在引用/回复群里的某条消息）"
                    else:
                        reply_context = "（此人在引用/回复群里的某条消息，但没附加文字）"

                messages, dyn_tokens = await build_conversation(
                    group_id, user_id, nickname, clean_cmd or cmd,
                    reply_context=reply_context,
                    reply_to_bot=reply_to_bot,
                )
                reply = await call_llm(messages, max_tokens=dyn_tokens, temperature=REPLY_TEMPERATURE)
                if reply:
                    await send_group_msg(ws, group_id, maybe_sticker(reply, group_id), reply_to=nickname)
                    history_key = (group_id, user_id)
                    if history_key not in conv_history:
                        conv_history[history_key] = deque(maxlen=MAX_CONV_ENTRIES)
                    conv_history[history_key].append({"role": "user", "name": nickname, "content": clean_cmd or cmd})
                    conv_history[history_key].append({"role": "assistant", "content": reply})
            else:
                print(f"[群{group_id}] {nickname}: {raw_msg[:60]}")
                await process_auto_reply(ws, group_id, user_id, nickname, raw_msg, now)
        except Exception as e:
            import traceback
            print(f"[错误] 处理消息失败 (群{group_id}): {e}")
            traceback.print_exc()
