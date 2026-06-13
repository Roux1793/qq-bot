---
name: system-admin
description: Ubuntu 服务器基础运维 (磁盘、内存、进程、网络、DNS)。服务器异常时触发。
---

# 服务器基础运维

## 快速体检

```bash
# 磁盘
df -h / && echo "---" && df -h /home

# 内存
free -h

# CPU/负载
uptime

# 进程 TOP 5
ps aux --sort=-%mem | head -6

# 端口监听
sudo ss -tlnp | grep -E "3000|3001|6099|8765|22"

# DNS 解析
nslookup api.deepseek.com 8.8.8.8
```

## DNS 修复（最常见）

```bash
# DNS 挂了 npm/pip/curl 都报 getaddrinfo/ETIMEDOUT
echo -e "[Resolve]\nDNS=8.8.8.8 114.114.114.114" | sudo tee /etc/systemd/resolved.conf
sudo systemctl restart systemd-resolved
```

## 包管理器修复

```bash
# npm 装不上包
npm config set registry https://registry.npmmirror.com/

# apt 更新失败
sudo apt update --fix-missing
```

## 进程管理

```bash
# 找僵尸进程
ps aux | grep defunct

# 杀指定进程
sudo kill -9 <PID>

# 按名称杀（慎用）
sudo pkill -f "进程名"
```

## 备份 Claude Code 原生包

```bash
mkdir -p ~/backup
cp -r /home/roux/.npm-global/lib/node_modules/@anthropic-ai/claude-code-linux-x64 ~/backup/ 2>/dev/null
# 恢复：cp -r ~/backup/claude-code-linux-x64 /home/roux/.npm-global/lib/node_modules/@anthropic-ai/
```

## 磁盘清理

```bash
# npm 缓存
npm cache clean --force

# journal 日志（保留 3 天）
sudo journalctl --vacuum-time=3d

# 大文件 top 10
du -sh /home/roux/* 2>/dev/null | sort -rh | head -10
```
