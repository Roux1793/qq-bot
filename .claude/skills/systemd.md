---
name: systemd
description: Bot 相关 systemd 服务管理 (napcat, qq-bot, remote-panel)。任何启停操作触发此技能。
---

# Bot systemd 服务管理

## 服务列表

| 服务 | 运行身份 | 作用 |
|------|---------|------|
| `napcat` | root | QQ 客户端 + OneBot |
| `qq-bot` | roux | Bot 桥接逻辑 |
| `remote-panel` | roux | Web 远程面板 :8765 |

## 一命令看全部

```bash
sudo systemctl status napcat qq-bot remote-panel --no-pager
```

## 标准操作

```bash
# 全部重启（最常见）
sudo systemctl restart napcat && sleep 30 && sudo systemctl restart qq-bot

# 单独操作
sudo systemctl stop qq-bot         # 只停 Bot
sudo systemctl start qq-bot        # 只启 Bot
sudo systemctl restart napcat      # 重启 QQ（被踢后）

# 查看是否有失败服务
sudo systemctl --failed
```

## 日志

```bash
sudo journalctl -u napcat --since "10 min ago" --no-pager
sudo journalctl -u qq-bot --since "10 min ago" --no-pager
```

## 注意

- `qq-bot` 绑定 `napcat`，napcat 停了 bot 会联动停止
- napcat 重启后需等 ~30 秒才能启 bot
- `remote-panel` 独立，不受其他服务影响
