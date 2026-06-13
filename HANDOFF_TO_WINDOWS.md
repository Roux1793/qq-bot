# Ubuntu 端已配置完毕，Windows 端待办

> 由 Ubuntu Claude Code 生成，2026-06-14

## Ubuntu 端已完成

### 基础环境
- [x] 中文输入法（fcitx5 全拼，Ctrl+Space 切换）
- [x] VS Code（Microsoft 官方源，`code` 启动）
- [x] Chromium 浏览器（PPA 源，非 snap）
- [x] Clash Verge 2.4.7（代理 HTTP:7897）

### 远程三件套
- [x] **Tailscale** 1.98.4 — 已装，**未登录**
- [x] **RustDesk** 1.4.7 — 已装，服务已启动自启
- [x] **Syncthing** 1.18.0 — 已装，用户服务已启动自启，Web 管理 `http://127.0.0.1:8384`
- [x] **SSH** — 已启用

### Claude Code 增强
- [x] Skills 10 个：`frontend-design`, `canvas-design`, `webapp-testing`, `web-artifacts-builder`, `doc-coauthoring`, `systematic-debugging`, `requesting-code-review`, `docx`, `pdf`, `translate`
- [x] MCP 3 个：`context7`, `github`, `playwright`
- [x] Git 全局代理已配（127.0.0.1:7897）

---

## Windows 端需要做的事

### 1. Tailscale — 组网（最重要，先做这个）

- 在 Windows 上下载安装：https://tailscale.com/download/windows
- 在 Ubuntu 终端获取登录链接：
  ```bash
  sudo tailscale up
  ```
- **把链接复制到 Windows 的浏览器打开**（Ubuntu 的 Chromium 代理不稳）
- 用 GitHub/Microsoft 账号登录同一账号
- 验证：Windows 上 `ping <ubuntu-tailscale-ip>` 能通即可

### 2. Syncthing — 文件同步

- 下载安装：https://syncthing.net/downloads/
- Ubuntu 设备 ID 获取：`syncthing --device-id`
- 互相添加设备，共享文件夹建议：`C:\Claude_code_test` ↔ `/home/roux/Claude_code_test`
- 走 Tailscale IP（Syncthing 会自动发现局域网设备）

### 3. RustDesk — 远程桌面

- 下载安装：https://rustdesk.com
- 在 Ubuntu 桌面打开 RustDesk 查看 ID 和密码
- Windows 端输入连接，建议走 Tailscale IP

### 4. VS Code Remote-SSH

- 装 VS Code + Remote-SSH 插件
- 连 `ssh roux@<ubuntu-tailscale-ip>`
- 终端里可直接跑 `claude`

---

## ⚠️ 重要提醒

**代理和 QQ Bot 冲突**：Clash 开全局/系统代理时，QQ Bot 的流量可能被误导向代理节点，导致 Bot 不可用。如果 Bot 出问题，优先检查：
- 关掉系统代理，或把 QQ Bot 流量直连（加 bypass 规则）
- Bot 相关端口：3001（WebSocket）、8765（Panel）

## 网络架构

```
Windows  ←──Tailscale VPN──→  Ubuntu
  ├─ Syncthing P2P 实时同步项目
  ├─ RustDesk 远程桌面
  └─ VS Code Remote-SSH 开发
```

## Ubuntu 信息

- 局域 IP: 192.168.1.8 / Tailscale 登录后获取私有 IP
- 用户: roux / sudo 密码: jianglong123
- Clash 代理: HTTP 127.0.0.1:7897
