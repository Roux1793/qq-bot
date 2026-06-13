# 读我 — Windows 端最新变更及待办

> 这份文件是 Windows 端的 Claude Code 留给你的。读完执行。

## 当前状态

- 已装 Kubuntu 桌面环境，有真实显示器 `DISPLAY=:0`
- Bot 三个 systemd 服务：napcat / qq-bot / remote-panel
- GitHub 仓库：`Roux1793/qq-bot`
- 有一条 30 分钟的自愈 cron 在跑
- 操作日志在 `/home/roux/claude-ops.log`

## 你需要做的事

### 1. 拉取最新代码
```bash
cd /home/roux/Claude_code_test && git pull origin master
```

### 2. 重新加载 napcat 服务（去掉了 xvfb）
```bash
sudo cp /home/roux/Claude_code_test/deploy/napcat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart napcat
```

### 3. 验证 QQ 在真实桌面启动成功
```bash
sleep 20
sudo systemctl status napcat --no-pager
ps aux | grep "opt/QQ/qq" | grep -v grep
ss -tlnp | grep -E "3000|3001|6099"
```
预期三个端口都在。

### 4. 确认 Bot 和面板都活着
```bash
sudo systemctl status napcat qq-bot remote-panel --no-pager
ss -tlnp | grep -E "3001|6099|8765"
```

### 5. 测试桌面环境下 QQ 窗口是否正常
```bash
DISPLAY=:0 xdotool search --name "QQ" 2>/dev/null
```
有输出说明 QQ 窗口在桌面正常渲染。

## 技能清单

`git pull` 后你的 `.claude/skills/` 下有 4 个技能：

| 技能 | 触发场景 |
|------|---------|
| `bot-guard` | Bot 挂了、被踢、需要验证 |
| `systemd` | 管理 napcat/qq-bot/remote-panel 启停 |
| `log-analysis` | Bot 没反应，排查日志 |
| `system-admin` | DNS 修复、磁盘清理、备份 |

## 重要提醒

- **别改 `qq_bot/config.py` 里的 `DEFAULT_PERSONAS`**，那只是兜底。真人设在 `/home/roux/personas.json`
- DNS 不稳定是老问题，修复命令在 `system-admin` 技能里
- Claude Code 原生包备份在 `~/backup/claude-code-linux-x64`
- 所有操作写进 `/home/roux/claude-ops.log`
