---
name: log-analysis
description: Bot 日志排查技能。用户报告异常时触发。
---

# Bot 日志分析

## 日志位置

| 日志 | 路径 | 权限 |
|------|------|------|
| Bot 桥接 | `/home/roux/bridge.log` | roux |
| QQ 客户端 | `/home/roux/qq.log` | root |
| 自愈脚本 | `/home/roux/claude-ops.log` | roux |
| 面板 | `/home/roux/panel.log` | roux |
| systemd | `journalctl -u napcat -u qq-bot` | sudo |

## 常见排查模式

### Bot 没反应
```bash
tail -30 /home/roux/bridge.log | grep -E "错误|异常|断开|超时"
```

### QQ 被踢
```bash
sudo grep -E "KickedOffLine|offline|kick|登录" /home/roux/qq.log | tail -10
```

### 需要短信验证
```bash
sudo grep proofWaterUrl /home/roux/qq.log | tail -3
```

### 自愈脚本最近干了什么
```bash
tail -20 /home/roux/claude-ops.log
```

### 端口不对
```bash
ss -tlnp | grep -E "3000|3001|6099|8765"
# 预期：3000(HTTP) 3001(WS) 6099(WebUI) 8765(Panel)
# 缺哪个哪个服务就有问题
```

## 快速判断

| 症状 | 查什么 |
|------|--------|
| @bot 不回复 | `bridge.log` 看 WS 是否断开 |
| 群消息无反应 | `ss` 看 3001 端口是否在 |
| WebUI 打不开 | `ss` 看 6099 端口是否在 |
| 面板打不开 | `ss` 看 8765 端口是否在 |
| QQ 反复掉线 | `qq.log` 搜 kick/offline |
