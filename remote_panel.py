#!/usr/bin/env python3
"""QQ Bot 远程控制面板 — 部署在 Ubuntu，Windows 浏览器访问 http://IP:8765"""
import http.server, json, os, re, subprocess, threading, time, uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8765
HOME = Path("/home/roux")
BOT_DIR = HOME / "qq-bot"
BRIDGE_LOG = HOME / "bridge.log"
QQ_LOG = HOME / "qq.log"
PANEL_LOG = HOME / "panel.log"
WEBUI_PORT = 6099
WEBUI_TOKEN = "7f44b9ec470a"
WEBUI_URL = f"http://127.0.0.1:{WEBUI_PORT}/webui?token={WEBUI_TOKEN}"
NAP_QQ = "/root/Napcat/opt/QQ/qq"
NAP_QQ_PATTERN = "/root/Napcat/opt/QQ/qq"
QQ_ACCOUNT = "2712841947"

_tasks: dict[str, dict] = {}
_tasks_lock = threading.Lock()

def _set_task(task_id, **kw):
    with _tasks_lock:
        if task_id in _tasks: _tasks[task_id].update(kw)

def _add_line(task_id, line):
    with _tasks_lock:
        if task_id in _tasks:
            _tasks[task_id]["lines"].append(line)
            _tasks[task_id]["progress"] = line

def run(cmd, timeout=10):
    try:
        r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "(timeout)", -1
    except Exception as e:
        return str(e), -1

def port_open(port):
    out, _ = run(f"ss -tlnp 2>/dev/null | grep -qE '[:]{port}\\s' && echo yes || echo no")
    return out == "yes"

def extract_verify_url():
    out, _ = run(f"sudo grep 'proofWaterUrl' {QQ_LOG} 2>/dev/null | tail -1")
    if out and "proofWaterUrl" in out:
        return out.strip()
    return None

def _run_start(task_id):
    try:
        # stop old bot
        _set_task(task_id, progress="停止旧 Bot 进程...")
        run("pgrep -f 'python.*qq_bot' | xargs -r kill 2>/dev/null", 3)

        # start bot
        _set_task(task_id, progress="启动 Bot 桥接...")
        subprocess.run(
            ["bash", "-c", f"cd {BOT_DIR} && python3 -u -m qq_bot > {BRIDGE_LOG} 2>&1 &"],
            timeout=5)
        time.sleep(3)

        # verify
        running, _ = run("pgrep -fc 'python.*qq_bot' 2>/dev/null")
        if int(running or 0) > 0:
            _set_task(task_id, status="done", progress="Bot 启动完成 ✓")
            _add_line(task_id, "Bot 进程已启动")
        else:
            _set_task(task_id, status="error", progress="Bot 启动失败，检查日志")
    except Exception as e:
        _set_task(task_id, status="error", progress=f"启动失败: {e}")

def _run_stop(task_id):
    try:
        _set_task(task_id, progress="停止 Bot...")
        run("pgrep -f 'python.*qq_bot' | xargs -r kill 2>/dev/null", 3)
        _add_line(task_id, "Bot 桥接已停止")
        _set_task(task_id, status="done", progress="Bot 已停止 ✓")
    except Exception as e:
        _set_task(task_id, status="error", progress=f"停止失败: {e}")

def _run_restart_bot(task_id):
    try:
        _run_stop(task_id)
        _set_task(task_id, status="running", lines=[], progress="重启中...")
        time.sleep(2)
        _run_start(task_id)
    except Exception as e:
        _set_task(task_id, status="error", progress=f"重启失败: {e}")

def _run_restart_qq(task_id):
    try:
        _set_task(task_id, progress="停止 QQ...")
        run(f"sudo pkill -f '{NAP_QQ_PATTERN}' 2>/dev/null", 3)
        time.sleep(3)
        _add_line(task_id, "旧 QQ 进程已停止")
        _set_task(task_id, progress="启动 QQ...")
        run(f"sudo screen -dmS napcat bash -c 'xvfb-run -a {NAP_QQ} --no-sandbox -q {QQ_ACCOUNT}'", 5)
        _add_line(task_id, "QQ 已重新启动，等待登录...")
        time.sleep(10)
        if port_open(WEBUI_PORT):
            _set_task(task_id, status="done", progress="QQ 重启完成 ✓ (WebUI 已就绪)")
        else:
            _set_task(task_id, status="done", progress="QQ 进程已重启，等待登录完成...")
    except Exception as e:
        _set_task(task_id, status="error", progress=f"重启 QQ 失败: {e}")

def _launch_task(action):
    task_id = uuid.uuid4().hex[:12]
    with _tasks_lock:
        _tasks[task_id] = {"status": "running", "progress": "准备中...", "lines": [], "action": action}
    fn = {"start": _run_start, "stop": _run_stop, "restart_bot": _run_restart_bot,
          "restart_qq": _run_restart_qq}.get(action)
    if fn:
        threading.Thread(target=fn, args=(task_id,), daemon=True).start()
    return task_id

# ====== HTML ======
PAGE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>QQ Bot 远程面板</title>
<style>
:root{--bg:#0d1117;--sidebar:#161b22;--card:#1c2129;--border:#30363d;--text:#e6edf3;--muted:#8b949e;--green:#3fb950;--red:#f85149;--blue:#58a6ff;--accent:#1f6feb;--hover:#1a2535;--radius:8px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:var(--bg);color:var(--text);display:flex;height:100vh;overflow:hidden}
.sidebar{width:200px;background:var(--sidebar);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.sidebar-brand{padding:18px 14px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}
.sidebar-brand .dot{width:10px;height:10px;border-radius:50%;background:var(--green);box-shadow:0 0 6px var(--green);flex-shrink:0;transition:background .3s}
.sidebar-brand .dot.off{background:var(--red);box-shadow:0 0 6px var(--red)}
.sidebar-title{font-size:14px;font-weight:600}
.sidebar-sub{font-size:10px;color:var(--muted)}
.sidebar-nav{flex:1;padding:8px;overflow-y:auto}
.nav-item{display:flex;align-items:center;gap:8px;padding:9px 10px;border-radius:6px;cursor:pointer;color:var(--muted);font-size:13px;transition:all .15s;border:none;background:none;width:100%;text-align:left;margin-bottom:1px}
.nav-item:hover{background:var(--hover);color:var(--text)}
.nav-item.active{background:var(--accent)!important;color:#fff!important}
.sidebar-footer{padding:10px;border-top:1px solid var(--border);font-size:10px;color:var(--muted)}
.main{flex:1;display:flex;flex-direction:column;overflow:hidden}
.toolbar{display:flex;align-items:center;justify-content:space-between;padding:10px 18px;border-bottom:1px solid var(--border);background:var(--sidebar);min-height:44px}
.toolbar h2{font-size:15px;font-weight:600}
.content-area{flex:1;overflow-y:auto;padding:16px}
.tab-panel{display:none}
.tab-panel.active{display:block}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;margin-bottom:14px}
.card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:14px}
.card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.card-header h3{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:600}
.status-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:5px}
.status-item{display:flex;align-items:center;justify-content:space-between;padding:6px 8px;background:var(--bg);border-radius:5px;font-size:11px}
.status-item .label{color:var(--muted)}
.status-item .value{font-weight:500}
.status-item .value.ok{color:var(--green)}
.status-item .value.err{color:var(--red)}
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-size:12px;cursor:pointer;transition:all .15s;white-space:nowrap;font-family:inherit}
.btn:hover{border-color:var(--accent);background:var(--hover)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{background:#388bfd}
.btn.danger{border-color:var(--red);color:var(--red)}
.btn.danger:hover{background:rgba(248,81,73,.1)}
.btn-group{display:flex;gap:6px;flex-wrap:wrap}
.progress-panel{display:none;margin-bottom:12px;padding:10px 14px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius)}
.progress-panel.active{display:block}
.progress-bar{height:4px;background:var(--border);border-radius:2px;overflow:hidden;margin-bottom:6px}
.progress-bar .fill{height:100%;background:var(--accent);width:0%;transition:width .3s}
.progress-text{font-size:11px;color:var(--muted)}
.log-viewer{background:#080c10;border:1px solid var(--border);border-radius:var(--radius);padding:12px;font-family:"Cascadia Code",Consolas,monospace;font-size:11px;line-height:1.5;height:380px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;color:var(--muted)}
.toast-container{position:fixed;bottom:16px;right:16px;z-index:1000;display:flex;flex-direction:column;gap:5px}
.toast{padding:8px 14px;border-radius:6px;font-size:12px;color:#fff;opacity:0;transition:all .3s}
.toast.in{opacity:1}
.toast.ok{background:var(--green)}.toast.err{background:var(--red)}.toast.info{background:var(--accent)}
.inline-input{background:var(--bg);border:1px solid var(--border);border-radius:6px;padding:6px 8px;color:var(--text);font-size:12px;width:100%;font-family:inherit}
.inline-input:focus{outline:none;border-color:var(--accent)}
.form-row{display:flex;gap:6px;margin-bottom:6px}
::-webkit-scrollbar{width:4px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
.copy-btn{background:none;border:none;color:var(--blue);cursor:pointer;font-size:11px;padding:2px 6px;border-radius:3px}
.copy-btn:hover{background:var(--hover)}
</style>
</head>
<body>
<div class="sidebar">
  <div class="sidebar-brand">
    <span class="dot" id="sideDot"></span>
    <div><div class="sidebar-title">Bot Panel</div><div class="sidebar-sub" id="sideStatus">加载中...</div></div>
  </div>
  <nav class="sidebar-nav">
    <button class="nav-item active" data-tab="dashboard">📊 仪表盘</button>
    <button class="nav-item" data-tab="control">⚙ 控制台</button>
    <button class="nav-item" data-tab="logs">📋 日志</button>
    <button class="nav-item" data-tab="tools">🔧 工具箱</button>
  </nav>
  <div class="sidebar-footer">v4.0 · 192.168.1.8:8765</div>
</div>
<div class="main">
  <div class="toolbar"><h2 id="tabTitle">仪表盘</h2><span style="font-size:11px;color:var(--muted)" id="clock"></span></div>
  <div class="content-area">

    <div class="tab-panel active" id="tab-dashboard">
      <div class="progress-panel" id="progressPanel">
        <div class="progress-bar"><div class="fill" id="progressFill"></div></div>
        <div class="progress-text" id="progressText">准备中...</div>
      </div>
      <div class="grid" style="grid-template-columns:1fr 240px 200px">
        <div class="card">
          <div class="card-header"><h3>系统状态</h3><span id="statusBadge" style="font-size:11px"></span></div>
          <div class="status-grid" id="statusGrid">加载中...</div>
        </div>
        <div class="card">
          <div class="card-header"><h3>快速操作</h3></div>
          <div style="display:flex;flex-direction:column;gap:6px">
            <button class="btn primary" onclick="quickAction('start')" style="justify-content:center">▶ 启动 Bot</button>
            <button class="btn" onclick="quickAction('restart_bot')" style="justify-content:center">↻ 重启 Bot</button>
            <button class="btn danger" onclick="quickAction('stop')" style="justify-content:center">⏹ 停止 Bot</button>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><h3>QQ 管理</h3></div>
          <div style="display:flex;flex-direction:column;gap:6px">
            <button class="btn" onclick="quickAction('restart_qq')" style="justify-content:center">🔄 重启 QQ</button>
            <button class="btn" onclick="openWebUI()" style="justify-content:center">🌐 打开 WebUI</button>
            <button class="btn" onclick="copyVerifyUrl()" id="btnVerify" style="justify-content:center;display:none">📱 复制验证链接</button>
          </div>
        </div>
      </div>
    </div>

    <div class="tab-panel" id="tab-control">
      <div class="progress-panel" id="progressPanel2">
        <div class="progress-bar"><div class="fill" id="progressFill2"></div></div>
        <div class="progress-text" id="progressText2">准备中...</div>
      </div>
      <div class="card" style="margin-bottom:12px">
        <div class="card-header"><h3>Bot 生命周期</h3></div>
        <div class="btn-group">
          <button class="btn primary" onclick="controlAction('start')">▶ 启动</button>
          <button class="btn" onclick="controlAction('restart_bot')">↻ 重启</button>
          <button class="btn danger" onclick="controlAction('stop')">⏹ 停止</button>
        </div>
      </div>
      <div class="card" style="margin-bottom:12px">
        <div class="card-header"><h3>QQ (NapCat)</h3></div>
        <div class="btn-group">
          <button class="btn" onclick="controlAction('restart_qq')">🔄 重启 QQ</button>
          <span style="font-size:11px;color:var(--muted);margin-left:8px">被踢后使用，约需20秒</span>
        </div>
      </div>
      <div class="card">
        <div class="card-header"><h3>说明</h3></div>
        <div style="font-size:11px;color:var(--muted);line-height:1.6">
          <p><strong>启动</strong> — 启动 Bot 桥接 (python -m qq_bot)，QQ 需已运行</p>
          <p><strong>停止</strong> — 终止 Bot 进程，不影响 QQ</p>
          <p><strong>重启 QQ</strong> — 杀掉并重启 NapCat QQ，Bot 会自动重连</p>
        </div>
      </div>
    </div>

    <div class="tab-panel" id="tab-logs">
      <div class="grid" style="grid-template-columns:1fr 1fr">
        <div class="card">
          <div class="card-header"><h3>Bot 日志 (bridge.log)</h3>
            <div class="btn-group"><button class="btn" onclick="refreshLog('bridge')" style="font-size:10px;padding:3px 8px">刷新</button></div>
          </div>
          <div class="log-viewer" id="logBridge">点击刷新加载...</div>
        </div>
        <div class="card">
          <div class="card-header"><h3>QQ 日志 (qq.log)</h3>
            <div class="btn-group"><button class="btn" onclick="refreshLog('qq')" style="font-size:10px;padding:3px 8px">刷新</button></div>
          </div>
          <div class="log-viewer" id="logQQ">点击刷新加载...</div>
        </div>
      </div>
    </div>

    <div class="tab-panel" id="tab-tools">
      <div class="grid" style="grid-template-columns:1fr 1fr">
        <div class="card">
          <div class="card-header"><h3>群管理</h3></div>
          <div class="form-row"><input class="inline-input" id="quickGroupId" placeholder="群号"></div>
          <div class="btn-group">
            <button class="btn" onclick="toolAction('silence')">🔇 禁言</button>
            <button class="btn" onclick="toolAction('restore')">🔊 恢复</button>
            <button class="btn" onclick="toolAction('stats')">📊 群统计</button>
          </div>
        </div>
        <div class="card">
          <div class="card-header"><h3>系统工具</h3></div>
          <div style="display:flex;flex-direction:column;gap:5px">
            <button class="btn" onclick="toolAction('dbstats')">💾 数据库统计</button>
            <button class="btn" onclick="toolAction('processes')">💻 进程列表</button>
            <button class="btn" onclick="toolAction('panel_log')">📄 面板日志</button>
          </div>
        </div>
      </div>
    </div>

  </div>
</div>
<div class="toast-container" id="toastContainer"></div>
<script>
document.querySelectorAll('.nav-item').forEach(function(item){
  item.addEventListener('click',function(){
    document.querySelectorAll('.nav-item').forEach(function(i){i.classList.remove('active')});
    item.classList.add('active');
    document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active')});
    document.getElementById('tab-'+item.dataset.tab).classList.add('active');
    document.getElementById('tabTitle').textContent={
      dashboard:'仪表盘',control:'控制台',logs:'日志',tools:'工具箱'}[item.dataset.tab]||item.dataset.tab;
    if(item.dataset.tab==='logs'){refreshLog('bridge');refreshLog('qq')}
  })
});

async function api(path,opt){
  opt=opt||{};
  try{var r=await fetch('/api/'+path,{method:opt.method||'GET',headers:{'Content-Type':'application/json'},body:opt.body||undefined});return await r.json()}
  catch(e){return {error:e.message}}
}

function toast(msg,type,dur){
  var c=document.getElementById('toastContainer'),d=document.createElement('div');
  d.className='toast '+(type||'info');d.textContent=msg;
  c.appendChild(d);requestAnimationFrame(function(){d.classList.add('in')});
  setTimeout(function(){d.classList.remove('in');setTimeout(function(){d.remove()},300)},dur||2500)
}

var _polTimer=null,_lastPct=0;
function showProgress(msg,pct,panelId){
  var id=panelId||'progressPanel';
  var p=document.getElementById(id);
  var f=document.getElementById(id==='progressPanel'?'progressFill':'progressFill2');
  var t=document.getElementById(id==='progressPanel'?'progressText':'progressText2');
  if(!p.classList.contains('active')){p.classList.add('active');_lastPct=0}
  var w=Math.max(_lastPct,Math.min(pct||(_lastPct+3),95));
  _lastPct=w;f.style.width=w+'%';t.textContent=msg
}
function hideProgress(ok,panelId){
  var id=panelId||'progressPanel';
  var f=document.getElementById(id==='progressPanel'?'progressFill':'progressFill2');
  f.style.width='100%';f.className=ok?'fill ok':'fill';
  setTimeout(function(){var p=document.getElementById(id);p.classList.remove('active');_lastPct=0;f.style.width='0%';f.className='fill'},1000)
}

function pollTask(taskId,panelId){
  if(_polTimer)clearInterval(_polTimer);
  _lastPct=0;
  _polTimer=setInterval(async function(){
    var r=await api('task/'+taskId);
    if(r.error){clearInterval(_polTimer);return}
    var pct=r.status==='done'?100:r.status==='error'?0:Math.min(90,_lastPct+5);
    showProgress(r.progress||'处理中...',pct,panelId);
    if(r.status==='done'){clearInterval(_polTimer);hideProgress(true,panelId);toast(r.progress,'ok');refreshStatus()}
    else if(r.status==='error'){clearInterval(_polTimer);hideProgress(false,panelId);toast(r.progress,'err')}
  },500)
}

async function quickAction(cmd){
  if(cmd==='webui'||cmd==='verify'){openWebUI();return}
  var r=await api(cmd,{method:'POST'});
  if(r.task_id){showProgress('执行中...',5);pollTask(r.task_id)}
  else{toast(r.error||'失败','err')}
}

async function controlAction(cmd){
  var r=await api(cmd,{method:'POST'});
  if(r.task_id){showProgress('执行中...',5,'progressPanel2');pollTask(r.task_id,'progressPanel2')}
  else{toast(r.error||'失败','err')}
}

function openWebUI(){
  window.open('http://192.168.1.8:6099/webui?token=7f44b9ec470a','_blank');
  toast('已打开 WebUI (需要 SSH 端口转发或本地访问)','info')
}

async function copyVerifyUrl(){
  var r=await api('verify_url');
  if(r.url){
    try{await navigator.clipboard.writeText(r.url);toast('验证链接已复制到剪贴板','ok')}
    catch(e){prompt('验证链接:',r.url)}
  }else{toast('当前无需验证','info')}
}

async function toolAction(cmd){
  var gid=document.getElementById('quickGroupId').value.trim();
  switch(cmd){
    case'silence':
      if(!gid){toast('请输入群号','err');return}
      var r=await api('silence',{method:'POST',body:JSON.stringify({group_id:gid})});
      toast(r.message||r.error||'OK',r.error?'err':'ok');break;
    case'restore':
      if(!gid){toast('请输入群号','err');return}
      r=await api('restore',{method:'POST',body:JSON.stringify({group_id:gid})});
      toast(r.message||r.error||'OK',r.error?'err':'ok');break;
    case'stats':
      if(!gid){toast('请输入群号','err');return}
      r=await api('group_stats',{method:'POST',body:JSON.stringify({group_id:gid})});
      toast(r.message||'无数据',r.error?'err':'ok');break;
    case'dbstats':
      r=await api('dbstats');toast(r.message||'无数据');break;
    case'processes':
      r=await api('processes');toast(r.message||'无数据');break;
    case'panel_log':
      r=await api('panel_log');toast(r.message||'无日志');break;
  }
}

async function refreshLog(type){
  var r=await api('logs/'+type);
  var el=document.getElementById(type==='bridge'?'logBridge':'logQQ');
  if(r.error){el.textContent='Error: '+r.error;return}
  el.textContent=r.lines||'(empty)';el.scrollTop=el.scrollHeight
}

async function refreshStatus(){
  var r=await api('status');
  var dot=document.getElementById('sideDot'),st=document.getElementById('sideStatus');
  var gd=document.getElementById('statusGrid'),bd=document.getElementById('statusBadge');
  var btnV=document.getElementById('btnVerify');
  if(r.error){
    dot.className='dot off';st.textContent='后端离线';
    gd.innerHTML='<span style="color:var(--red)">无法获取状态</span>'
    document.getElementById('clock').textContent=new Date().toLocaleTimeString();
    return
  }
  dot.className='dot '+(r.bot_running?'':'off');
  st.textContent=r.bot_running?'Bot 在线':'Bot 离线';
  bd.innerHTML=r.bot_running?'<span style="color:var(--green)">● 在线</span>':'<span style="color:var(--red)">● 离线</span>';
  btnV.style.display=r.needs_verify?'flex':'none';
  var items=[
    ['Bot 桥接',r.bot_running,1],['QQ 客户端',r.qq_running,1],
    ['WS (3001)',r.port3001,1],['HTTP (3000)',r.port3000,1],['WebUI (6099)',r.port6099,1],
    ['QQ 进程数',r.qq_count||'0',0],
  ];
  gd.innerHTML=items.map(function(i){
    var k=i[0],v=i[1],crit=i[2];
    var cls=(crit===1)?(v?'ok':'err'):'';
    var val=(crit===1)?(v?'运行中':'停止'):v;
    return'<div class="status-item"><span class="label">'+k+'</span><span class="value '+cls+'">'+val+'</span></div>'
  }).join('');
  document.getElementById('clock').textContent=new Date().toLocaleTimeString()
}
setInterval(refreshStatus,5000);refreshStatus();
</script>
</body>
</html>"""

# ====== HTTP Handler ======
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _query(self):
        return parse_qs(urlparse(self.path).query)

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/":
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/status":
            bridge_out, _ = run("pgrep -fc 'python.*qq_bot' 2>/dev/null")
            bot_running = int(bridge_out.strip() or 0) > 0
            qq_out, _ = run(f"sudo pgrep -fc '{NAP_QQ_PATTERN}' 2>/dev/null")
            qq_running = int(qq_out.strip() or 0) > 0
            qq_count, _ = run(f"sudo pgrep -fc '{NAP_QQ_PATTERN}' 2>/dev/null")
            vu = extract_verify_url()
            self._json({
                "bot_running": bot_running,
                "qq_running": qq_running,
                "qq_count": qq_count.strip(),
                "port3001": port_open(3001),
                "port3000": port_open(3000),
                "port6099": port_open(WEBUI_PORT),
                "needs_verify": bool(vu),
            })
            return

        if path == "/api/logs/bridge":
            n = 100 if "tail" in self._query() else 60
            out, _ = run(f"tail -{n} {BRIDGE_LOG} 2>/dev/null")
            self._json({"lines": out or "(empty)"})
            return

        if path == "/api/logs/qq":
            out, _ = run(f"sudo tail -40 {QQ_LOG} 2>/dev/null")
            self._json({"lines": out or "(empty)"})
            return

        if path == "/api/verify_url":
            vu = extract_verify_url()
            if vu:
                m = re.search(r'https://\S+', vu)
                self._json({"url": m.group(0) if m else vu})
            else:
                self._json({"url": None, "message": "当前无需验证"})
            return

        if path == "/api/dbstats":
            out, _ = run(f"cd {BOT_DIR} && python3 -c 'from qq_bot.db import db_stats; print(db_stats())' 2>/dev/null")
            self._json({"message": out or "无法获取统计"})
            return

        if path == "/api/processes":
            out, _ = run("ps aux | grep -E 'qq_bot|opt/QQ/qq' | grep -v grep")
            self._json({"message": out or "无相关进程"})
            return

        if path == "/api/panel_log":
            out, _ = run(f"tail -40 {PANEL_LOG} 2>/dev/null")
            self._json({"message": out or "(无日志)"})
            return

        if path.startswith("/api/task/"):
            task_id = path.split("/")[-1]
            with _tasks_lock:
                task = _tasks.get(task_id)
            self._json(task if task else {"error": "task not found"}, 404 if not task else 200)
            return

        self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = urlparse(self.path).path

        if path in ("/api/start", "/api/stop", "/api/restart_bot", "/api/restart_qq"):
            task_id = _launch_task(path.split("/")[-1])
            self._json({"task_id": task_id, "message": "任务已创建"})
            return

        if path == "/api/restart":
            # Unified: stop bot, restart QQ, then start bot
            task_id = _launch_task("restart_bot")
            self._json({"task_id": task_id, "message": "重启 Bot 任务已创建"})
            return

        if path == "/api/silence":
            data = self._body()
            gid = data.get("group_id", "").strip()
            if gid:
                out, _ = run(f"cd {BOT_DIR} && python3 -c \"from qq_bot.state import silenced_groups; from qq_bot.send import save_silenced; silenced_groups.add({gid}); save_silenced(); print('群 {gid} 已禁言')\" 2>/dev/null")
                self._json({"message": out or f"群 {gid} 已禁言"})
            else:
                self._json({"error": "请输入群号"}, 400)
            return

        if path == "/api/restore":
            data = self._body()
            gid = data.get("group_id", "").strip()
            if gid:
                out, _ = run(f"cd {BOT_DIR} && python3 -c \"from qq_bot.state import silenced_groups; from qq_bot.send import save_silenced; silenced_groups.discard({gid}); save_silenced(); print('群 {gid} 已恢复')\" 2>/dev/null")
                self._json({"message": out or f"群 {gid} 已恢复"})
            else:
                self._json({"error": "请输入群号"}, 400)
            return

        if path == "/api/group_stats":
            data = self._body()
            gid = data.get("group_id", "").strip()
            if gid:
                out, _ = run(f"cd {BOT_DIR} && python3 -c \"from qq_bot.db import get_stats; import json; s=get_stats({gid}); print(json.dumps(s,ensure_ascii=False))\" 2>/dev/null")
                if out:
                    try:
                        s = json.loads(out)
                        lines = [f"群 {gid} 统计：共 {s.get('total',0)} 条消息，收录 {s.get('days',0)} 天"]
                        top = s.get("top_users", [])
                        if top:
                            lines.append("话痨排行: " + ", ".join(f"{n}({c})" for n, c in top[:5]))
                        self._json({"message": "\n".join(lines)})
                    except Exception:
                        self._json({"message": out})
                else:
                    self._json({"message": "暂无数据"})
            else:
                self._json({"error": "请输入群号"}, 400)
            return

        self._json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

def main():
    print(f"[Panel v4.0] http://0.0.0.0:{PORT}", flush=True)
    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == "__main__":
    main()
