---
name: bot-guard
description: QQ Bot 状态监控、一键排障、被踢重登、日志分析。任何 Bot 相关操作触发此技能。
---

# QQ Bot 运维技能

## 架构速查

  NapCat → WS:3001 → qq_bot → DeepSeek API
  面板端口: 8765 | WebUI: 6099 | HTTP: 3000

## TL;DR 状态检查

  sudo systemctl status napcat qq-bot remote-panel --no-pager
  ss -tlnp | grep -E '3001|8765|6099'

## 被踢重登（最常用）

  1. sudo grep proofWaterUrl /home/roux/qq.log | tail -1  → 获取 SMS 链接
  2. 把链接发给用户用浏览器验证
  3. 验证后 NapCat 自动恢复，Bot 通过 systemd 自动重连
  4. 如果不行：sudo systemctl restart napcat && sleep 30 && sudo systemctl restart qq-bot

## 日志速查

  Bot:    tail -50 /home/roux/bridge.log
  QQ:     sudo tail -50 /home/roux/qq.log
  systemd: sudo journalctl -u napcat -u qq-bot --since "10 min ago" --no-pager

## 自愈脚本

  手动执行: bash /home/roux/Claude_code_test/deploy/qq-bot-healthcheck.sh
  日志:     tail -20 /home/roux/claude-ops.log

## 关键路径

  代码:    /home/roux/Claude_code_test/qq_bot/
  NapCat:  /root/Napcat/opt/QQ/qq
  NapCat配置: /root/Napcat/opt/QQ/resources/app/app_launcher/napcat/config/
  数据:    /home/roux/ (.env, personas.json, chat_history.db)
  运维手册: /home/roux/Claude_code_test/DEPLOY.md

## 修改代码后

  cd /home/roux/Claude_code_test && git add/commit/push  → 同步到 GitHub
  sudo systemctl restart qq-bot  → 重载生效
