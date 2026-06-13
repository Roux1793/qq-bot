#!/bin/bash
# QQ Bot 自愈检查 — 每30分钟由 crontab 执行
LOG="/home/roux/claude-ops.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

# === 1. DNS 检查 ===
if ! timeout 5 nslookup api.deepseek.com > /dev/null 2>&1; then
    log "DNS 解析失败，尝试修复..."
    echo -e "[Resolve]\nDNS=8.8.8.8 114.114.114.114" | sudo -n tee /etc/systemd/resolved.conf > /dev/null 2>&1
    sudo -n systemctl restart systemd-resolved 2>/dev/null
    if timeout 5 nslookup api.deepseek.com > /dev/null 2>&1; then
        log "DNS 已修复"
    else
        log "DNS 修复失败，需要手动 sudo"
    fi
fi

# === 2. Bot WebSocket 端口检查 (3001 是 NapCat) ===
if ! ss -tlnp 2>/dev/null | grep -q 3001; then
    log "QQ Bot WebSocket 端口 3001 无响应"
    # 尝试用已有的 NOPASSWD sudo 重启 NapCat
    sudo -n pkill -f /root/Napcat/opt/QQ/qq 2>/dev/null
    sleep 5
    sudo -n /usr/bin/screen -dmS napcat bash -c "xvfb-run -a /root/Napcat/opt/QQ/qq --no-sandbox -q 2712841947" 2>/dev/null
    sleep 20
    if ss -tlnp 2>/dev/null | grep -q 3001; then
        log "NapCat 已恢复"
    else
        log "NapCat 恢复失败，需要手动介入"
    fi
fi

# === 3. Bot 桥接进程检查 ===
if ! pgrep -f "python.*qq_bot" > /dev/null 2>&1; then
    log "Bot 桥接进程不在，启动中..."
    systemctl --user restart qq-bot 2>/dev/null
    if pgrep -f "python.*qq_bot" > /dev/null 2>&1; then
        log "qq-bot 已恢复"
    else
        log "qq-bot 启动失败"
        # 尝试直接启动
        cd /home/roux/Claude_code_test && nohup /usr/bin/python3 -m qq_bot >> /home/roux/bridge.log 2>&1 &
        log "qq-bot 已通过 nohup 启动"
    fi
fi

# === 4. 面板检查 ===
if ! pgrep -f "remote_panel" > /dev/null 2>&1; then
    log "remote-panel 进程不在，尝试恢复..."
    systemctl --user restart remote-panel 2>/dev/null
    # 用户面板是系统级服务，尝试 sudo
    sudo -n systemctl restart remote-panel 2>/dev/null
    if pgrep -f "remote_panel" > /dev/null 2>&1; then
        log "remote-panel 已恢复"
    else
        log "remote-panel 恢复失败"
    fi
fi
