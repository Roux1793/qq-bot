# Ubuntu 端已配置完毕，Windows 端待办

> 由 Ubuntu Claude Code 生成，2026-06-14

## Ubuntu 端已完成

### 基础环境
- [x] 中文输入法（fcitx5 全拼，Ctrl+Space 切换）
- [x] VS Code（Microsoft 官方源，`code` 启动）
- [x] Chromium 浏览器（PPA 源，非 snap）
- [x] Clash Verge 2.4.7（代理已配置，HTTP:7897, Socks:7898）

### 远程三件套
- [x] **Tailscale** 1.98.4 — 已装，需登录
- [x] **RustDesk** 1.4.7 — 已装，服务已启动自启
- [x] **Syncthing** 1.18.0 — 已装，用户服务已启动自启，Web 管理 `http://127.0.0.1:8384`
- [x] **SSH** — 已启用

### Claude Code 增强
- [x] Skills: `frontend-design`, `canvas-design`, `webapp-testing`, `web-artifacts-builder`, `doc-coauthoring`, `systematic-debugging`, `requesting-code-review` 以及原有的 `docx/image/math/ocr/pdf/translate`
- [x] MCP: `context7`（实时文档）, `github`（repo 操作）, `playwright`（浏览器自动化）
- [x] Git 全局代理已配置（127.0.0.1:7897）

---

## Windows 端需要做的事

### 1. Tailscale — 组网（最重要）
- 下载安装：https://tailscale.com/download/windows
- 登录同一账号
- Ubuntu 端登录链接：`https://login.tailscale.com/a/53758c501a50f`（12 小时内有效，过期后运行 `sudo tailscale up` 重新获取）
- 验证：`ping <ubuntu-tailscale-ip>` 能通即成功

### 2. Syncthing — 文件同步
- 下载安装：https://syncthing.net/downloads/
- 打开 Web 管理 `http://127.0.0.1:8384`
- 添加 Ubuntu 设备 ID（Ubuntu 上 `syncthing --device-id` 查看）
- 添加共享文件夹（例如 `C:\Claude_code_test` ↔ `/home/roux/Claude_code_test`）

### 3. RustDesk — 远程桌面
- 下载安装：https://rustdesk.com
- 连 Ubuntu 的 RustDesk ID（Ubuntu 桌面打开 RustDesk 查看）
- 建议走 Tailscale IP 连接，速度更快

### 4. VS Code Remote-SSH
- 装 VS Code + Remote-SSH 插件
- 连 `ssh roux@<ubuntu-tailscale-ip>`
- 终端里可直接运行 `claude` 操作 Ubuntu

---

## 网络架构

```
Windows  ←──Tailscale VPN──→  Ubuntu
  ├─ Syncthing P2P 实时同步 Claude_code_test
  ├─ RustDesk 远程桌面
  └─ VS Code Remote-SSH 开发
```

## Ubuntu 信息

- IP: 192.168.1.8（局域）/ Tailscale 登录后获取私有 IP
- 用户: roux / sudo 密码: jianglong123
- Clash 代理: HTTP 127.0.0.1:7897, Socks 127.0.0.1:7898
