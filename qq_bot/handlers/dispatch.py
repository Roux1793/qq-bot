"""核心消息分发 + WebSocket 连接管理"""
import asyncio
import json
import os
import re
import sys
from collections import deque
from datetime import datetime, timedelta

import websockets

from ..config import (WS_URL, ADMIN_QQ, STYLE_UPDATE_INTERVAL,
                       MAX_CONV_TURNS, MAX_CONV_ENTRIES, GROUP_CONTEXT_LINES,
                       MAX_REPLY_TOKENS, REPLY_TEMPERATURE)
from ..state import (_ws, _kicked_offline_detected,
                      _health_check_failures, msg_buffer, last_msg_time,
                      silenced_groups, priv_summary_state, conv_history,
                      active_persona, last_summary)
from ..db import init_db, save_message, cleanup_old_messages, db_stats
from ..permissions import (is_admin, group_has_perm, group_admin_enabled,
                            group_admin_public, get_persona_for_group,
                            save_active_personas)
from ..send import (send_group_msg, send_private_msg, maybe_sticker,
                     load_json, load_personas, load_auto_reply_rules,
                     load_silenced)
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
from ..web_search import search_web, should_search, format_search_results
from ..knowledge_search import search as kb_search, should_query_kb, format_kb_results, build_grounding_prompt


# ====== WebSocket 连接 ======

async def connect_ws():
    global _ws
    retry = 0
    was_previously_connected = False
    while True:
        try:
            print(f"[WS] 连接 {WS_URL} ...")
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10, max_size=2**23) as ws:
                _ws = ws
                print("[WS] 已连接")
                retry = 0
                global _health_check_failures, _kicked_offline_detected
                _health_check_failures = 0
                _kicked_offline_detected = False
                if was_previously_connected and ADMIN_QQ:
                    print("[WS] 断开重连成功，通知管理员...")
                    for admin in ADMIN_QQ:
                        await send_private_msg(ws, admin,
                            f"[Bot重连通知]\n时间: {datetime.now().strftime('%m-%d %H:%M:%S')}\nWS已重新连接到NapCat")
                    was_previously_connected = False
                await handle_messages(ws)
        except (websockets.ConnectionClosed, OSError) as e:
            if _ws is not None:
                was_previously_connected = True
            _ws = None
            retry += 1
            delay = min(retry * 5, 60)
            print(f"[WS] 断开: {e}，{delay}s 后重连")
            await asyncio.sleep(delay)


# ====== 核心消息处理 ======

async def handle_messages(ws):
    global _kicked_offline_detected, _health_check_failures
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
                if "kick" in reason.lower() or "kick" in sub.lower():
                    print("[状态] 检测到 KickedOffLine！标记假死，将触发自动重启...")
                    _kicked_offline_detected = True
                for admin in ADMIN_QQ:
                    await send_private_msg(ws, admin,
                        f"[Bot离线通知]\n时间: {datetime.now().strftime('%m-%d %H:%M:%S')}\n"
                        f"原因: {reason}\n"
                        f"{'已标记假死，健康检查将自动重启NapCat' if _kicked_offline_detected else 'Bot将自动尝试重连...'}")
            elif sub in ("connect", "online"):
                _kicked_offline_detected = False
                _health_check_failures = 0
                print(f"[状态] QQ 已上线 ({sub})")
                for admin in ADMIN_QQ:
                    await send_private_msg(ws, admin,
                        f"[Bot上线通知]\n时间: {datetime.now().strftime('%m-%d %H:%M:%S')}\n状态: 已重新连接")
            continue

        # client_status 通知
        if data.get("post_type") == "notice" and data.get("notice_type") == "client_status":
            client_info = data.get("client", {})
            is_online = client_info.get("online", True)
            if not is_online:
                print(f"[状态] QQ客户端离线 (client_status)，标记假死...")
                _kicked_offline_detected = True
            else:
                _kicked_offline_detected = False
                _health_check_failures = 0
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
                    from ..send import save_silenced as do_save
                    do_save()
                    await send_private_msg(ws, user_id, f"群 {gid} 已禁言 ✓")
                    print(f"[禁言] 群{gid} 已 silence (管理员私聊)")
                else:
                    silenced_groups.discard(gid)
                    from ..send import save_silenced as do_save
                    do_save()
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
                from ..fetch import _sync_to_db
                from ..db import get_stats
                await _sync_to_db(gid)
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
        msg_buffer[group_id].append(f"[{ts}] {nickname}: {raw_msg}")

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
                # 真管理员永远有管理员权限；普通用户需群开启 admin_enabled + admin_public
                effective_admin = real_admin or (admin_enabled and admin_public)

                # === help ===
                if re.search(r"help|帮助|命令|功能", cmd):
                    if not group_has_perm(group_id, "help"):
                        continue
                    if effective_admin:
                        await send_group_msg(ws, group_id, HELP_TEXT + "\n\n" + ADMIN_HELP)
                    else:
                        await send_group_msg(ws, group_id, HELP_TEXT)

                # === 搜索（全员可用）===
                elif re.search(r"搜索|查找|搜", cmd):
                    if not group_has_perm(group_id, "search"):
                        continue
                    await handle_search(ws, group_id, cmd)

                # === 人设（切换/修改/创建=管理员，列表/详情/查看=全员）===
                elif re.search(r"切换|人设|修改人设|创建人设", cmd):
                    is_readonly = not re.search(r"切换|修改|创建", cmd)
                    if is_readonly:
                        # 只读：人设列表 / 人设详情 / 当前人设
                        await handle_persona(ws, group_id, user_id, cmd)
                    elif effective_admin:
                        await handle_persona(ws, group_id, user_id, cmd)
                    else:
                        await send_group_msg(ws, group_id, "权限不足。切换/修改/创建人设需要管理员权限。\n全员可用：@bot 人设列表 / 人设详情 <名称>")

                # === 统计（全员可用）===
                elif re.search(r"统计|排行|活跃", cmd):
                    if not group_has_perm(group_id, "stats"):
                        continue
                    await handle_stats(ws, group_id)

                # === 总结（全员可用）===
                elif re.search(r"总结|汇总|整理", cmd):
                    if not group_has_perm(group_id, "summary"):
                        continue
                    await handle_summary(ws, group_id, user_id, cmd, now)

                # === 知识库（回忆/列表=全员，提取=管理员）===
                elif re.search(r"回忆|知识点|知识列表", cmd):
                    # 只读查询：全员可用
                    await handle_knowledge(ws, group_id, cmd)

                elif re.search(r"提取知识|分析知识", cmd):
                    if not effective_admin:
                        await send_group_msg(ws, group_id, "权限不足。提取知识需要管理员权限。")
                    else:
                        await handle_admin(ws, group_id, user_id, cmd)

                # === 规则管理（加/删=管理员，列表=全员）===
                elif re.search(r"规则列表|查看规则", cmd):
                    # 只读：全员可用
                    await handle_admin(ws, group_id, user_id, cmd)

                elif re.search(r"加规则|删规则", cmd):
                    if not effective_admin:
                        await send_group_msg(ws, group_id, "权限不足。管理规则需要管理员权限。")
                    else:
                        await handle_admin(ws, group_id, user_id, cmd)

                # === 禁言/恢复（管理员）===
                elif re.search(r"^silence$|^静音$|^闭嘴$", cmd):
                    if not effective_admin:
                        await send_group_msg(ws, group_id, "权限不足。")
                    else:
                        silenced_groups.add(group_id)
                        from ..send import save_silenced as do_save
                        do_save()
                        await send_group_msg(ws, group_id, "已静默，不再主动发言。管理员私聊我「群号 恢复」或群里@我说「恢复」即可。")
                        print(f"[禁言] 群{group_id} 已 silence")

                elif re.search(r"^恢复$|^解除$|^说话$", cmd):
                    if not effective_admin:
                        await send_group_msg(ws, group_id, "权限不足。")
                    else:
                        silenced_groups.discard(group_id)
                        from ..send import save_silenced as do_save
                        do_save()
                        await send_group_msg(ws, group_id, "已恢复发言 ✓")
                        print(f"[禁言] 群{group_id} 已恢复")

                elif cmd.startswith("admin"):
                    if not effective_admin:
                        await send_group_msg(ws, group_id, "权限不足。")
                    else:
                        await handle_admin(ws, group_id, user_id, cmd)

                # === LLM 自由对话（全员可用）===
                else:
                    # LLM 自由对话
                    if not group_has_perm(group_id, "chat"):
                        continue

                    # ── 解析 QQ 引用（reply）──
                    reply_context = ""
                    clean_cmd = cmd
                    reply_match = re.match(r"^\[CQ:reply,id=(-?\d+)\]", cmd)
                    if reply_match:
                        reply_id = reply_match.group(1)
                        clean_cmd = cmd[reply_match.end():].strip()
                        # 尝试从 msg_buffer 中找被引用的原始消息
                        buf_list = list(msg_buffer.get(group_id, deque(maxlen=60)))
                        quoted_text = None
                        # 遍历最近的消息，找可能的被引用内容（按时间邻近）
                        for line in reversed(buf_list[:-1]):  # 排除当前消息自己
                            m = re.match(r"\[\d\d:\d\d\] (.+?): (.+)", line)
                            if m:
                                quoted_text = f"「{m.group(1)}」说过：{m.group(2)}"
                                break  # 取最近一条非Bot消息
                        if quoted_text:
                            reply_context = f"（此人在回复 {quoted_text}）"
                        elif clean_cmd:
                            reply_context = "（此人在引用/回复群里的某条消息）"
                        else:
                            reply_context = "（此人在引用/回复群里的某条消息，但没附加文字）"

                    # ── 知识库检索（BanG Dream相关问题优先）──
                    kb_context = ""
                    kb_grounding = ""
                    kb_query = should_query_kb(clean_cmd or cmd)
                    if kb_query:
                        print(f"[知识库] 触发检索: 「{kb_query}」")
                        kb_results = kb_search(kb_query, top_n=3)
                        kb_context = format_kb_results(kb_results)
                        kb_grounding = build_grounding_prompt(kb_results)

                    # ── 联网搜索（按需触发，作为补充）──
                    search_context = ""
                    search_query = should_search(clean_cmd or cmd)
                    if search_query:
                        print(f"[搜索] 触发搜索: 「{search_query}」")
                        results = await search_web(search_query, num=5)
                        search_context = format_search_results(results)

                    # ── 构建 system prompt：人设 + 群聊指导 + 思考增强 ──
                    persona = get_persona_for_group(group_id)
                    system_msg = (
                        persona["system_prompt"]
                        + f"\n\n## 当前对话者\n"
                        + f"正在对你说话的人是「{nickname}」(QQ:{user_id})。你必须回复ta。\n"
                        + f"【重要】用QQ号区分人：群里有昵称相似的人时，靠QQ号（{user_id}）来区分，不要搞混。\n"
                        + f"【重要】跨群隔离：你在这个群的对话和你与其他群的对话完全独立。不要把在别的群发生的事带到这个群来。\n"
                        + f"\n## 回复准则\n"
                        + f"1. 像真人聊天一样自然回应，长短由对方说话内容决定，不要客套模板。\n"
                        + f"2. 人设是你的底色但不是牢笼——群友聊什么你就跟着聊，不要拒绝参与话题。\n"
                        + f"3. 群里有多个不同的人，回复某人时要考虑其他人说了什么，综合判断。\n"
                        + f"4. 语气有变化，有时冷静有时热情，不要每条都emoji或感叹号。\n"
                        + f"5. 遇到不确定的事实问题，如有搜索结果就参考，没有就坦诚说不知道。"
                    )
                    if kb_context:
                        system_msg += f"\n\n{kb_context}"
                    if kb_grounding:
                        system_msg += f"\n\n{kb_grounding}"
                    if search_context:
                        system_msg += f"\n\n{search_context}"
                    messages = [{"role": "system", "content": system_msg}]

                    # ── 对话历史（标注说话人）──
                    history_key = (group_id, user_id)
                    history = conv_history.get(history_key)
                    if history:
                        for h in list(history):
                            if h["role"] == "user":
                                speaker = h.get("name", str(user_id))
                                messages.append({"role": "user", "content": f"「{speaker}」说：{h['content']}"})
                            else:
                                messages.append({"role": h["role"], "content": h["content"]})

                    # ── 群聊环境（扩展上下文 + 标注所有说话人）──
                    buf = list(msg_buffer.get(group_id, deque(maxlen=60)))
                    recent = buf[-GROUP_CONTEXT_LINES:] if len(buf) >= GROUP_CONTEXT_LINES else buf
                    ctx_text = ""
                    if recent:
                        # 组装群聊上下文，标注每个说话人的身份（昵称+QQ号）
                        lines = []
                        for line in recent:
                            m = re.match(r"\[\d\d:\d\d\] (.+?):", line)
                            speaker_in_line = m.group(1) if m else ""
                            if speaker_in_line == nickname:
                                lines.append(line + f"  ← 当前在对你说话 (QQ:{user_id})")
                            elif speaker_in_line:
                                lines.append(line)
                            else:
                                lines.append(line)

                        # 识别最近有哪些不同的人在说话（列出QQ号区分相似昵称）
                        speakers_in_context = set()
                        for line in recent:
                            m = re.match(r"\[\d\d:\d\d\] (.+?):", line)
                            if m: speakers_in_context.add(m.group(1))

                        ctx_text = (
                            f"## 群聊实时环境（共{len(lines)}条，说话人：{', '.join(speakers_in_context)}）\n"
                            + "\n".join(lines)
                            + f"\n\n## 你的任务\n"
                            + f"「{nickname}」在对你说话"
                            + (f"。{reply_context}" if reply_context else "")
                            + f"。请综合群聊环境和你的对话历史，自然地回复。\n"
                            + f"回复要求：像真人聊天一样，长短由内容决定，不要客套模板。"
                        )
                        messages.append({"role": "user", "content": f"{ctx_text}\n{clean_cmd}"})
                    else:
                        msg_text = f"「{nickname}」对你说：{clean_cmd}"
                        if reply_context:
                            msg_text = f"「{nickname}」{reply_context}：{clean_cmd}"
                        messages.append({"role": "user", "content": msg_text})

                    # ── 自适应 max_tokens：根据上下文长度动态调整 ──
                    ctx_len = len(clean_cmd or "") + sum(len(m["content"]) for m in messages)
                    if ctx_len < 500:
                        dyn_tokens = 300
                    elif ctx_len < 1500:
                        dyn_tokens = 500
                    elif ctx_len < 3000:
                        dyn_tokens = 700
                    else:
                        dyn_tokens = MAX_REPLY_TOKENS

                    reply = await call_llm(messages, max_tokens=dyn_tokens, temperature=REPLY_TEMPERATURE)
                    if reply:
                        await send_group_msg(ws, group_id, maybe_sticker(reply))
                        if history_key not in conv_history:
                            conv_history[history_key] = deque(maxlen=MAX_CONV_ENTRIES)
                        conv_history[history_key].append({"role": "user", "name": nickname, "content": clean_cmd or cmd})
                        conv_history[history_key].append({"role": "assistant", "content": reply})
            else:
                print(f"[群{group_id}] {nickname}: {raw_msg[:60]}")
                await process_auto_reply(ws, group_id, user_id, nickname, raw_msg, now)
        except Exception as e:
            print(f"[错误] 处理消息失败 (群{group_id}): {e}")
