# QQ Bot Ubuntu 端完整运维手册

> 适用场景：Windows 端远程 SSH 登录 Ubuntu 服务器，部署、调试、维护 QQ Bot。
> 服务器 IP: `192.168.1.8` | 用户: `roux` | 系统: Ubuntu 22.04

---

## 目录
1. [SSH 连接](#1-ssh-连接)
2. [服务总览](#2-服务总览)
3. [日常运维命令](#3-日常运维命令)
4. [启动 / 停止 / 重启](#4-启动--停止--重启)
5. [查看日志 & 排查问题](#5-查看日志--排查问题)
6. [QQ 验证问题（最常见故障）](#6-qq-验证问题最常见故障)
7. [代码更新 & 同步](#7-代码更新--同步)
8. [人设管理](#8-人设管理)
9. [数据库 & 数据文件](#9-数据库--数据文件)
10. [远程面板 (Web)](#10-远程面板-web)
11. [韧性自愈机制](#11-韧性自愈机制)
12. [故障速查表](#12-故障速查表)
13. [重要文件路径速查](#13-重要文件路径速查)
14. [常见操作 step-by-step](#14-常见操作-step-by-step)

---

## 1. SSH 连接

```bash
# 从 Windows 终端（CMD/PowerShell/Git Bash）
ssh roux@192.168.1.8
# 密码: jianglong123

# sudo 密码: jianglong123
```

**如果连不上**：检查服务器是否开机、IP 是否变动（路由器 DHCP）。

---

## 2. 服务总览

| 服务名 | 管理方式 | 作用 | 端口 |
|--------|----------|------|------|
| `napcat` | systemd（系统级，root 运行） | QQ 客户端 + OneBot WebSocket | 3001 (WS), 6099 (WebUI) |
| `qq-bot` | systemd（系统级，roux 运行） | Bot 桥接逻辑 | 无（客户端） |
| `remote-panel` | systemd（系统级） | Web 远程控制面板 | 8765 |

**关键依赖链**：`napcat` → `qq-bot`（Bot 依赖 NapCat 的 WebSocket；NapCat 停则 Bot 停）

---

## 3. 日常运维命令

```bash
# 查看所有服务状态（一条命令）
sudo systemctl status napcat qq-bot remote-panel --no-pager

# 查看端口是否在监听
ss -tlnp | grep -E '3001|8765|6099'
# 预期看到 3001 (NapCat WS), 8765 (Panel)

# 查看进程
ps aux | grep -E 'opt/QQ/qq|python.*qq_bot|remote_panel'
```

---

## 4. 启动 / 停止 / 重启

```bash
# ========== 全部重启（最常用） ==========
sudo systemctl restart napcat          # 重启 QQ 客户端（等 30 秒让它启动完）
sleep 30
sudo systemctl restart qq-bot          # 重启 Bot 桥接

# ========== 单独操作 ==========
sudo systemctl stop qq-bot             # 停止 Bot（QQ 继续在线）
sudo systemctl start qq-bot            # 启动 Bot
sudo systemctl restart qq-bot          # 重启 Bot

sudo systemctl stop napcat             # 停止 QQ（Bot 会自动停止）
sudo systemctl start napcat            # 启动 QQ
sudo systemctl restart napcat          # 重启 QQ

# ========== 查看某服务详细状态 ==========
sudo systemctl status napcat -l --no-pager
sudo systemctl status qq-bot -l --no-pager

# ========== 查看是否开机自启 ==========
sudo systemctl is-enabled napcat qq-bot remote-panel
# 应该都显示 "enabled"
```

**注意**：`napcat` 启动慢（QQ 客户端 + xvfb 虚拟桌面），给 30-60 秒。启动后 3001 端口出现才说明 OneBot 就绪。

---

## 5. 查看日志 & 排查问题

```bash
# ========== systemd 日志（最近 50 行） ==========
sudo journalctl -u napcat -n 50 --no-pager
sudo journalctl -u qq-bot -n 50 --no-pager
sudo journalctl -u remote-panel -n 50 --no-pager

# ========== 实时跟踪日志 ==========
sudo journalctl -u napcat -f          # Ctrl+C 退出
sudo journalctl -u qq-bot -f

# ========== 应用日志（文件） ==========
tail -50 ~/bridge.log                  # Bot 桥接日志
tail -50 ~/qq.log                      # QQ 客户端日志
tail -50 ~/panel.log                   # 面板日志
tail -50 ~/claude-ops.log              # 运维操作日志

# ========== 按时间过滤 ==========
sudo journalctl -u qq-bot --since "10 minutes ago" --no-pager
sudo journalctl -u napcat --since "2026-06-13 12:00" --no-pager
```

---

## 6. QQ 验证问题（最常见故障）

### 症状
- WebUI (6099) 能打开，但 3001 端口不监听
- Bot 连不上 WebSocket，日志报 `Connection refused`
- 原因：QQ 触发了安全验证（滑块/扫码），OneBot 服务被阻塞

### 诊断
```bash
# 1. 检查 3001 端口
ss -tlnp | grep 3001
# 如果没有输出 → OneBot 未启动

# 2. 打开 WebUI 看验证页面
# 浏览器访问: http://192.168.1.8:6099/webui?token=7f44b9ec470a
# 看是否有滑块/二维码验证页面
```

### 解决
1. 浏览器打开 `http://192.168.1.8:6099/webui?token=7f44b9ec470a`
2. 完成验证（滑块 or 扫码）
3. 验证通过后，3001 端口会在 10-30 秒内自动出现
4. Bot 会自动重连（健康检查每 90 秒探测一次）
5. 验证是否恢复：
```bash
ss -tlnp | grep 3001                    # 应出现
sudo journalctl -u qq-bot -n 10 --no-pager   # 应看到 "connected" 之类
```

### 如果 WebUI 也打不开
```bash
# 重新启动 NapCat
sudo systemctl restart napcat
sleep 40
# 再访问 WebUI
```

---

## 7. 代码更新 & 同步

### 自动更新（已配置）
- **每天凌晨 3 点**自动 `git pull`，有更新则自动重启 Bot
- 日志记录在 `~/claude-ops.log`

### 手动更新（从 Windows 推代码后）
```bash
# 在 Windows 端 push 代码后，SSH 到 Ubuntu 执行：
cd ~/qq-bot
git pull
sudo systemctl restart qq-bot
```

### 两个仓库说明
| 仓库 | 路径 | GitHub | 用途 |
|------|------|--------|------|
| Claude_code_test | `~/Claude_code_test/` | `Roux1793/Claude_code_test` | 实际运行代码（与 Windows 同步） |
| qq-bot | `~/qq-bot/` | `Roux1793/qq-bot` | Ubuntu 部署文件（含 deploy/） |

**注意**：两个仓库都有 `qq_bot/` 模块和 `remote_panel.py`，但 `config.py` 的 DEFAULT_PERSONAS 不同（Ubuntu 端有自己维护的人设）。代码逻辑应该通过 GitHub 同步，人设配置各自维护。

### 手动同步 Claude_code_test
```bash
cd ~/Claude_code_test
git pull
sudo systemctl restart qq-bot
```

---

## 8. 人设管理

### 当前人设（Ubuntu 端 config.py 内置）
- `default` — 小助手（温和耐心）
- `tsundere` — 傲娇猫娘
- `chuunibyou` — 中二病魔王

### 人设文件
```bash
cat ~/personas.json          # 自定义人设
cat ~/active_personas.json   # 各群当前活跃人设
```

### 通过 QQ 群管理
```
@bot 人设列表        — 查看可用人设
@bot 人设详情 XX     — 查看某个人设
@bot 切换 XX         — 切换当前群人设（管理员）
@bot 创建人设 ...    — 创建自定义人设（管理员）
```

---

## 9. 数据库 & 数据文件

```bash
# 聊天历史（SQLite）
ls -lh ~/chat_history.db

# 查看数据库统计
python3 -c "
import sqlite3
db = sqlite3.connect('/home/roux/chat_history.db')
cursor = db.execute('SELECT COUNT(*) FROM messages')
print(f'消息总数: {cursor.fetchone()[0]}')
tables = db.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()
print(f'表: {[t[0] for t in tables]}')
db.close()
"

# 其他数据文件
ls -lh ~/auto_reply.json       # 关键词自动回复规则
ls -lh ~/group_perms.json      # 群权限
ls -lh ~/silenced_groups.json  # 禁言群
ls -lh ~/group_styles.json     # 群风格
```

---

## 10. 远程面板 (Web)

```
地址: http://192.168.1.8:8765
```

### 功能
- 查看 Bot 运行状态
- 启动/停止/重启 Bot
- 重启 QQ 客户端
- 切换群聊人设
- 禁言/恢复指定群
- 查看 Bot 日志

### 面板挂了怎么修
```bash
sudo systemctl restart remote-panel
sudo systemctl status remote-panel --no-pager
```

---

## 11. 韧性自愈机制

### 三层守护

```
第一层: systemd Restart=always
  └─ 进程崩溃 → 15 秒内自动拉起

第二层: crontab 每 30 分钟健康检查
  └─ DNS → 端口 3001 → Bot 进程 → Panel 状态
  └─ 任何一项挂了 → 尝试自动恢复

第三层: StartLimit 熔断
  └─ napcat: 10 分钟内最多重启 5 次
  └─ qq-bot: 5 分钟内最多重启 10 次
  └─ 超过限制 → 停止重启，防止无限循环
```

### 自愈脚本
```bash
# 手动执行健康检查
bash ~/qq-bot-healthcheck.sh

# 查看自愈历史
grep -E "DNS|端口|恢复|重启" ~/claude-ops.log | tail -20
```

### 健康检查覆盖项
1. DNS 解析 `api.deepseek.com` 是否正常
2. NapCat WebSocket 端口 3001 是否监听
3. Bot 桥接进程是否存活
4. 远程面板进程是否存活

---

## 12. 故障速查表

| 症状 | 可能原因 | 快速修复 |
|------|----------|----------|
| Bot 不回消息 | Bot 进程死了 | `sudo systemctl restart qq-bot` |
| Bot 不回消息 + 3001 端口不在 | QQ 掉了 | `sudo systemctl restart napcat`，等 30s |
| 3001 端口不在但 QQ 在线 | QQ 触发验证 | 打开 WebUI 6099 完成验证 |
| `api.deepseek.com` 解析失败 | DNS 问题 | 自动修复，或 `sudo systemctl restart systemd-resolved` |
| 面板打不开 (8765) | Panel 进程死了 | `sudo systemctl restart remote-panel` |
| Bot 回复但内容奇怪 | LLM API 问题 | 检查 `~/.env` 中 DEEPSEEK_API_KEY |
| git pull 失败 | SSL 证书问题 | 已设 `http.sslVerify false`，若仍失败检查网络 |
| 磁盘空间不足 | 日志文件过大 | `ls -lh ~/bridge.log ~/qq.log ~/panel.log` |

---

## 13. 重要文件路径速查

```
# 代码
/home/roux/Claude_code_test/qq_bot/     — 实际运行代码
/home/roux/qq-bot/qq_bot/               — 部署仓库代码
/home/roux/qq-bot/deploy/               — systemd 服务文件 + 脚本

# 配置
/home/roux/.env                          — 环境变量 (API Key, Admin QQ, WS URL)
/home/roux/personas.json                 — 自定义人设
/home/roux/active_personas.json          — 各群活跃人设
/home/roux/auto_reply.json               — 关键词自动回复
/home/roux/group_perms.json              — 群权限

# 数据
/home/roux/chat_history.db               — SQLite 聊天历史 (保留 14 天)
/home/roux/silenced_groups.json          — 禁言群列表
/home/roux/group_styles.json             — 群风格

# 日志
/home/roux/bridge.log                    — Bot 桥接日志
/home/roux/qq.log                        — QQ 客户端日志
/home/roux/panel.log                     — 远程面板日志
/home/roux/claude-ops.log               — 运维操作日志

# 服务
/etc/systemd/system/napcat.service       — NapCat systemd 服务
/etc/systemd/system/qq-bot.service       — Bot systemd 服务
/etc/systemd/system/remote-panel.service — 面板 systemd 服务
/etc/cron.d/qq-bot                       — 自愈 cron 配置

# NapCat
/root/Napcat/opt/QQ/qq                   — QQ 可执行文件
/root/Napcat/opt/QQ/resources/app/app_launcher/napcat/config/
  ├── napcat.json                        — 主配置
  ├── onebot11_2712841947.json           — OneBot 网络 (HTTP/WS 端口!)
  ├── napcat_2712841947.json             — 账号配置
  └── webui.json                         — WebUI Token

# 备份
/home/roux/backup/claude-code-linux-x64/ — Claude Code 原生包备份 (239M)
```

---

## 14. 常见操作 step-by-step

### 场景 A：Bot 完全没反应了
```bash
# Step 1: 查看状态
sudo systemctl status napcat qq-bot --no-pager

# Step 2: 查看端口
ss -tlnp | grep 3001

# Step 3a: 如果 QQ 在但 Bot 不在 → 只重启 Bot
sudo systemctl restart qq-bot

# Step 3b: 如果 QQ 不在 → 全重启
sudo systemctl restart napcat
sleep 30
sudo systemctl restart qq-bot

# Step 4: 确认恢复
ss -tlnp | grep 3001          # 应看到端口
sudo systemctl status qq-bot --no-pager   # 应显示 active
```

### 场景 B：Windows 改了代码，同步到 Ubuntu
```bash
# 在 Windows: git push 之后
# SSH 到 Ubuntu:
cd ~/Claude_code_test && git pull
sudo systemctl restart qq-bot
```

### 场景 C：需要查 Bot 为什么没回复某条消息
```bash
# 看 Bot 最新日志
tail -100 ~/bridge.log

# 看最近 5 分钟日志
sudo journalctl -u qq-bot --since "5 minutes ago" --no-pager

# 搜索特定关键词
grep -i "error\|exception\|timeout\|fail" ~/bridge.log | tail -20
```

### 场景 D：重启服务器后验证一切正常
```bash
# 等服务器启动完成（约 2 分钟），然后：
sudo systemctl status napcat qq-bot remote-panel --no-pager
ss -tlnp | grep -E '3001|8765'
# 三个服务都应该 active，两个端口都在监听
```

### 场景 E：修改人设
```bash
# 用 QQ 命令（推荐）
@bot 切换 tsundere       # 切到傲娇猫娘
@bot 切换 default        # 切回小助手

# 或修改 personas.json 后重启 Bot
nano ~/personas.json
sudo systemctl restart qq-bot
```

### 场景 F：Claude Code 启动报 "native binary not installed"
```bash
# 恢复原生包
cp -r ~/backup/claude-code-linux-x64 ~/.npm-global/lib/node_modules/@anthropic-ai/
node ~/.npm-global/lib/node_modules/@anthropic-ai/claude-code/install.cjs
```

---

## 附录：服务器信息

| 项目 | 值 |
|------|-----|
| IP | 192.168.1.8 |
| 用户 | roux |
| sudo 密码 | jianglong123 |
| QQ 号 | 2712841947 |
| QQ 密码 | jianglong123 |
| NapCat WebUI | http://192.168.1.8:6099/webui?token=7f44b9ec470a |
| 远程面板 | http://192.168.1.8:8765 |
| GitHub 用户 | Roux1793 |
| 运维日志 | `/home/roux/claude-ops.log` |
