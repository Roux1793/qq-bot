#!/bin/bash
# QQ Bot 每日更新 — 每天凌晨 3 点 git pull 并重启
LOG="/home/roux/claude-ops.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG"; }

cd /home/roux/Claude_code_test || exit 1

# 检查是否是 git 仓库
if [ ! -d .git ]; then
    log "不是 git 仓库，跳过更新"
    exit 0
fi

BEFORE=$(git rev-parse HEAD 2>/dev/null)

# 拉取更新
if git pull --ff-only origin main 2>&1 | tee -a "$LOG"; then
    AFTER=$(git rev-parse HEAD 2>/dev/null)
    if [ "$BEFORE" != "$AFTER" ]; then
        log "代码有更新，重启 qq-bot..."
        sudo systemctl restart qq-bot
        log "qq-bot 已重启"
    else
        log "代码无更新"
    fi
else
    log "git pull 失败，可能网络不通或仓库未配置"
fi
