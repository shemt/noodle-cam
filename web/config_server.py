import json
import logging
import time
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, send_from_directory, Response

from config.settings import Config

logger = logging.getLogger(__name__)

NAV_BAR = """
<div style="background:#333;color:#fff;padding:10px 20px;margin:-20px -20px 20px -20px;">
    <a href="/" style="color:#fff;text-decoration:none;margin-right:20px;font-weight:bold;">配置</a>
    <a href="/monitor" style="color:#fff;text-decoration:none;margin-right:20px;font-weight:bold;">监控</a>
    <a href="/recordings" style="color:#fff;text-decoration:none;font-weight:bold;">录像管理</a>
</div>
"""

CONFIG_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>NoodleCam 配置</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .container { display: flex; gap: 20px; flex-wrap: wrap; }
        .panel { background: #fff; padding: 16px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); flex: 1; min-width: 360px; }
        label { display: block; margin: 10px 0 4px; font-weight: bold; }
        input, select, textarea { width: 100%; padding: 8px; box-sizing: border-box; }
        button { padding: 8px 16px; margin: 4px 4px 4px 0; cursor: pointer; border-radius: 4px; border: 1px solid #ccc; }
        .btn-primary { background: #007bff; color: white; border: none; }
        .success { color: green; }
        .error { color: red; }
        #msg { margin-top: 10px; font-weight: bold; }
    </style>
</head>
<body>
    """ + NAV_BAR + """
    <h1>NoodleCam 参数配置</h1>
    <div class="container">
        <div class="panel">
            <h2>参数微调</h2>
            <label>YOLO 置信度阈值</label>
            <input type="number" id="confidence" step="0.05" min="0" max="1" value="{{ confidence }}">
            <label>多帧投票 N</label>
            <input type="number" id="vote_frames" value="{{ vote_frames }}">
            <label>投票通过 M</label>
            <input type="number" id="vote_threshold" value="{{ vote_threshold }}">
            <label>防抖时间（秒）</label>
            <input type="number" id="debounce" step="0.1" value="{{ debounce }}">

            <h2 style="margin-top:20px;">语音播报文字</h2>
            <label>客户靠近</label>
            <input type="text" id="msg_customer" value="{{ msg_customer }}">
            <label>放碗检测</label>
            <input type="text" id="msg_bowl_placed" value="{{ msg_bowl_placed }}">
            <label>餐品就绪</label>
            <input type="text" id="msg_meal_ready" value="{{ msg_meal_ready }}">
            <label>取碗完成</label>
            <input type="text" id="msg_bowl_removed" value="{{ msg_bowl_removed }}">

            <h2 style="margin-top:20px;">模式切换</h2>
            <label>工作模式</label>
            <select id="llm_enabled">
                <option value="false" {{ 'selected' if not llm_enabled else '' }}>本地模式</option>
                <option value="true" {{ 'selected' if llm_enabled else '' }}>LLM 备用模式</option>
            </select>

            <div style="margin-top:20px;">
                <button class="btn-primary" onclick="saveConfig()">保存配置</button>
            </div>
            <div id="msg"></div>
        </div>

        <div class="panel">
            <h2>配置 JSON 预览</h2>
            <textarea id="configPreview" rows="20" readonly style="font-family:monospace;font-size:12px;"></textarea>
        </div>
    </div>

    <script>
    function buildPayload() {
        return {
            confidence: parseFloat(document.getElementById('confidence').value),
            vote_frames: parseInt(document.getElementById('vote_frames').value),
            vote_threshold: parseInt(document.getElementById('vote_threshold').value),
            debounce: parseFloat(document.getElementById('debounce').value),
            llm_enabled: document.getElementById('llm_enabled').value === 'true',
            messages: {
                customer_approach: document.getElementById('msg_customer').value,
                bowl_placed: document.getElementById('msg_bowl_placed').value,
                meal_ready: document.getElementById('msg_meal_ready').value,
                bowl_removed: document.getElementById('msg_bowl_removed').value
            }
        };
    }
    function updatePreview() {
        const data = buildPayload();
        document.getElementById('configPreview').value = JSON.stringify({
            vision: {
                confidence_threshold: data.confidence,
                vote_frames: data.vote_frames,
                vote_threshold: data.vote_threshold,
                debounce_seconds: data.debounce
            },
            audio: { messages: data.messages },
            llm: { enabled: data.llm_enabled }
        }, null, 2);
    }
    function saveConfig() {
        const data = buildPayload();
        fetch('/api/config', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        }).then(r => r.json()).then(res => {
            const msg = document.getElementById('msg');
            msg.innerText = res.message;
            msg.className = res.success ? 'success' : 'error';
        }).catch(err => {
            const msg = document.getElementById('msg');
            msg.innerText = '保存失败: ' + err;
            msg.className = 'error';
        });
    }
    fetch('/api/config').then(r => r.json()).then(cfg => {
        updatePreview();
    });
    document.querySelectorAll('input, select').forEach(el => {
        el.addEventListener('change', updatePreview);
        el.addEventListener('input', updatePreview);
    });
    </script>
</body>
</html>
"""

MONITOR_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>NoodleCam 监控</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }
        h1, h2 { color: #333; margin-top: 0; }
        .container { display: flex; gap: 20px; flex-wrap: wrap; }
        .panel { background: #fff; padding: 16px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .panel-left { flex: 2; min-width: 480px; }
        .panel-right { flex: 1; min-width: 320px; }
        .video-wrap {
            position: relative; display: inline-block; border: 1px solid #ccc;
            background: #000; overflow: hidden; width: 100%; max-width: {{ width }}px;
        }
        .video-wrap img { display: block; width: 100%; height: auto; }
        .stat-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }
        .stat-card { background: #f8f9fa; padding: 10px; border-radius: 6px; text-align: center; border-left: 4px solid #007bff; }
        .stat-card.recording-on { border-left-color: #28a745; }
        .stat-card.recording-off { border-left-color: #dc3545; }
        .stat-value { font-size: 20px; font-weight: bold; color: #333; }
        .stat-label { font-size: 11px; color: #666; margin-top: 2px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
        th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }
        th { background: #f8f9fa; }
        .empty { color: #999; padding: 16px; text-align: center; }
        .btn-primary { background: #007bff; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .btn-danger { background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .btn-secondary { background: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .mode-active { background: #28a745 !important; color: white !important; border-color: #28a745 !important; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }
        .badge-person { background: #d4edda; color: #155724; }
        .badge-bowl { background: #fff3cd; color: #856404; }
        .video-wrap {
            position: relative; display: inline-block; border: 1px solid #ccc;
            background: #000; overflow: hidden; width: 100%; max-width: {{ width }}px;
        }
        .video-wrap img { display: block; width: 100%; height: auto; }
        .video-wrap canvas {
            position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            cursor: crosshair; z-index: 2;
        }
        .overlay-label {
            position: absolute; top: 4px; left: 4px; color: #0f0; z-index: 3;
            font-size: 12px; background: rgba(0,0,0,0.6); padding: 2px 6px; border-radius: 3px;
            pointer-events: none;
        }
        .roi-tag {
            display: inline-block; padding: 3px 8px; margin: 3px 3px 0 0;
            border-radius: 4px; font-size: 12px; background: #e9ecef; border: 1px solid #dee2e6;
        }
        .roi-tag .del { color: #dc3545; cursor: pointer; margin-left: 6px; font-weight: bold; }
        .info { color: #666; font-size: 12px; margin: 4px 0; }
        .section { margin-bottom: 20px; }
    </style>
</head>
<body>
    """ + NAV_BAR + """
    <h1>NoodleCam 实时监控</h1>
    <div class="container">
        <div class="panel panel-left">
            <div class="section">
                <h2>实时画面</h2>
                <div class="video-wrap" id="videoWrap">
                    <img id="videoFeed" src="/video_feed" alt="实时视频流">
                    <canvas id="roiCanvas" width="{{ width }}" height="{{ height }}"></canvas>
                    <div class="overlay-label">模式: <span id="modeLabel">客户检测区</span></div>
                </div>
                <p class="info">分辨率: {{ width }}x{{ height }} | 在画面上方拖拽框选 ROI 区域</p>
                <div style="margin-top:8px;">
                    <button id="btnCustomer" class="mode-active" onclick="setMode('customer')">客户检测区</button>
                    <button id="btnBowl" onclick="setMode('bowl')">碗位检测区</button>
                    <button class="btn-secondary" onclick="clearAll()">清空全部</button>
                    <button class="btn-primary" onclick="saveRoi()">保存 ROI</button>
                </div>
                <div style="margin-top:8px;">
                    <label style="font-weight:bold;font-size:13px;">已设定区域</label>
                    <div id="roiList"></div>
                </div>
                <div id="roiMsg" style="margin-top:8px;font-weight:bold;"></div>
            </div>
        </div>

        <div class="panel panel-right">
            <div class="section">
                <h2>系统概览</h2>
                <div class="stat-grid">
                    <div class="stat-card">
                        <div class="stat-value" id="stateVal">--</div>
                        <div class="stat-label">当前状态</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="fpsVal">--</div>
                        <div class="stat-label">FPS</div>
                    </div>
                    <div class="stat-card" id="recCard">
                        <div class="stat-value" id="recVal">--</div>
                        <div class="stat-label">录像</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="detVal">--</div>
                        <div class="stat-label">检测目标</div>
                    </div>
                </div>
                <div style="margin-top:12px;">
                    <button id="recToggle" class="btn-primary" onclick="toggleRecording()">加载中...</button>
                </div>
            </div>

            <div class="section">
                <h2>检测目标</h2>
                <div id="detTableWrap">
                    <div class="empty">暂无检测数据</div>
                </div>
            </div>
        </div>
    </div>

    <script>
    // ========== ROI Canvas ==========
    const canvas = document.getElementById('roiCanvas');
    const ctx = canvas.getContext('2d');
    let mode = 'customer';
    let isDrawing = false;
    let startX = 0, startY = 0;
    let currentRect = null;
    let customerRoi = null;
    let bowlRois = [];
    let scaleX = 1, scaleY = 1;

    function updateScale() {
        const rect = canvas.getBoundingClientRect();
        scaleX = canvas.width / rect.width;
        scaleY = canvas.height / rect.height;
    }
    function clearCanvas() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    function drawRoi(roi, color, label) {
        const {x1, y1, x2, y2} = roi;
        ctx.strokeStyle = color; ctx.lineWidth = 3;
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
        ctx.fillStyle = color;
        ctx.font = 'bold 14px sans-serif';
        ctx.fillText(label, x1 + 4, y1 + 18);
        ctx.fillStyle = color.replace(')', ', 0.15)').replace('rgb', 'rgba');
        ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
    }
    function redraw() {
        clearCanvas();
        if (customerRoi) drawRoi(customerRoi, 'rgb(0, 200, 0)', '客户区');
        bowlRois.forEach(r => drawRoi(r, 'rgb(255, 165, 0)', '碗位#' + r.id));
        if (currentRect) drawRoi(currentRect, 'rgb(0, 150, 255)', '框选中');
        updateRoiList();
    }
    function setMode(m) {
        mode = m;
        document.getElementById('btnCustomer').classList.toggle('mode-active', m === 'customer');
        document.getElementById('btnBowl').classList.toggle('mode-active', m === 'bowl');
        document.getElementById('modeLabel').textContent = m === 'customer' ? '客户检测区' : '碗位检测区';
    }
    function getMousePos(e) {
        updateScale();
        const rect = canvas.getBoundingClientRect();
        return { x: Math.round((e.clientX - rect.left) * scaleX), y: Math.round((e.clientY - rect.top) * scaleY) };
    }
    canvas.addEventListener('mousedown', e => {
        const pos = getMousePos(e);
        startX = pos.x; startY = pos.y;
        isDrawing = true;
        currentRect = {x1: startX, y1: startY, x2: startX, y2: startY};
        redraw();
    });
    canvas.addEventListener('mousemove', e => {
        if (!isDrawing) return;
        const pos = getMousePos(e);
        currentRect = { x1: Math.min(startX, pos.x), y1: Math.min(startY, pos.y), x2: Math.max(startX, pos.x), y2: Math.max(startY, pos.y) };
        redraw();
    });
    canvas.addEventListener('mouseup', e => {
        if (!isDrawing) return;
        isDrawing = false;
        const pos = getMousePos(e);
        const rect = { x1: Math.min(startX, pos.x), y1: Math.min(startY, pos.y), x2: Math.max(startX, pos.x), y2: Math.max(startY, pos.y) };
        currentRect = null;
        if (rect.x2 - rect.x1 < 10 || rect.y2 - rect.y1 < 10) { redraw(); return; }
        if (mode === 'customer') {
            customerRoi = rect;
        } else {
            const id = bowlRois.length + 1;
            const name = prompt('请输入碗位编号（如 1, 2, 3）:', id);
            if (name === null) { redraw(); return; }
            bowlRois.push({id: parseInt(name) || id, x1: rect.x1, y1: rect.y1, x2: rect.x2, y2: rect.y2});
        }
        redraw();
    });
    canvas.addEventListener('mouseleave', () => { if (isDrawing) { isDrawing = false; currentRect = null; redraw(); } });
    function removeBowlRoi(idx) { bowlRois.splice(idx, 1); redraw(); }
    function clearAll() {
        if (!confirm('确定清空所有 ROI 设定吗？')) return;
        customerRoi = null; bowlRois = []; redraw();
    }
    function updateRoiList() {
        const el = document.getElementById('roiList');
        let html = '';
        if (customerRoi) {
            html += `<div class="roi-tag" style="border-color:#28a745;background:#d4edda;">客户区: (${customerRoi.x1},${customerRoi.y1})-(${customerRoi.x2},${customerRoi.y2}) <span class="del" onclick="customerRoi=null;redraw();">&times;</span></div>`;
        }
        bowlRois.forEach((r, i) => {
            html += `<div class="roi-tag" style="border-color:#fd7e14;background:#fff3cd;">碗位#${r.id}: (${r.x1},${r.y1})-(${r.x2},${r.y2}) <span class="del" onclick="removeBowlRoi(${i});redraw();">&times;</span></div>`;
        });
        if (!customerRoi && bowlRois.length === 0) html = '<span style="color:#999;font-size:12px;">暂无设定区域</span>';
        el.innerHTML = html;
    }
    async function saveRoi() {
        const payload = {
            customer_roi: customerRoi ? JSON.stringify(customerRoi) : JSON.stringify({x1:0,y1:0,x2:0,y2:0}),
            bowl_rois: JSON.stringify(bowlRois)
        };
        try {
            const res = await fetch('/api/config', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)
            });
            const data = await res.json();
            const msg = document.getElementById('roiMsg');
            msg.innerText = data.message;
            msg.className = data.success ? 'success' : 'error';
        } catch (e) {
            document.getElementById('roiMsg').innerText = '保存失败: ' + e;
        }
    }
    // 加载现有 ROI
    fetch('/api/config').then(r => r.json()).then(cfg => {
        if (cfg.vision && cfg.vision.customer_roi) {
            const cr = cfg.vision.customer_roi;
            if (cr.x2 > cr.x1 && cr.y2 > cr.y1) customerRoi = cr;
        }
        if (cfg.vision && cfg.vision.bowl_rois) bowlRois = cfg.vision.bowl_rois;
        redraw();
    });
    function fitCanvas() {
        const container = document.getElementById('videoWrap');
        const maxW = Math.min(container.parentElement.clientWidth - 40, canvas.width);
        const ratio = canvas.height / canvas.width;
        container.style.width = maxW + 'px';
    }
    window.addEventListener('resize', fitCanvas);
    fitCanvas();
    redraw();

    // ========== Status polling ==========
    let lastRecordEnabled = null;
    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            updateUI(await res.json());
        } catch (e) { console.error('状态获取失败:', e); }
    }
    function updateUI(data) {
        document.getElementById('stateVal').textContent = data.state || 'UNKNOWN';
        document.getElementById('fpsVal').textContent = data.fps || 0;
        document.getElementById('detVal').textContent = (data.detections || []).length;
        const recText = data.recording ? '录制中' : (data.record_enabled ? '待命' : '已关闭');
        document.getElementById('recVal').textContent = recText;
        document.getElementById('recCard').className = 'stat-card ' + (data.recording ? 'recording-on' : (data.record_enabled ? '' : 'recording-off'));
        if (lastRecordEnabled !== data.record_enabled) {
            lastRecordEnabled = data.record_enabled;
            const btn = document.getElementById('recToggle');
            btn.textContent = data.record_enabled ? '关闭录像' : '开启录像';
            btn.className = data.record_enabled ? 'btn-danger' : 'btn-primary';
        }
        const wrap = document.getElementById('detTableWrap');
        const dets = data.detections || [];
        if (dets.length === 0) {
            wrap.innerHTML = '<div class="empty">当前未检测到目标</div>';
        } else {
            let html = '<table><tr><th>类别</th><th>置信度</th><th>边界框</th></tr>';
            dets.forEach(d => {
                const bc = d.class === 'person' ? 'badge-person' : (d.class === 'bowl' ? 'badge-bowl' : '');
                html += `<tr><td><span class="badge ${bc}">${d.class}</span></td><td>${d.conf}</td><td>[${d.bbox.join(', ')}]</td></tr>`;
            });
            html += '</table>';
            wrap.innerHTML = html;
        }
    }
    async function toggleRecording() {
        const newEnabled = !lastRecordEnabled;
        try {
            const res = await fetch('/api/recording', {
                method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({enabled: newEnabled})
            });
            const data = await res.json();
            if (data.success) { lastRecordEnabled = newEnabled; fetchStatus(); }
        } catch (e) { alert('切换失败: ' + e); }
    }
    fetchStatus();
    setInterval(fetchStatus, 1000);
    </script>
</body>
</html>
"""

RECORDINGS_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>NoodleCam 录像管理</title>
    <style>
        body { font-family: sans-serif; margin: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .panel { background: #fff; padding: 16px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); max-width: 900px; }
        table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: left; }
        th { background: #f8f9fa; }
        .btn-primary { background: #007bff; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .btn-danger { background: #dc3545; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .empty { color: #999; padding: 30px; text-align: center; }
        .size { color: #666; font-family: monospace; }
        .mtime { color: #666; font-size: 13px; }
    </style>
</head>
<body>
    """ + NAV_BAR + """
    <h1>录像文件管理</h1>
    <div class="panel">
        <div id="fileListWrap">
            <div class="empty">正在加载...</div>
        </div>
    </div>

    <script>
    async function loadFiles() {
        try {
            const res = await fetch('/api/recordings');
            const data = await res.json();
            renderFiles(data.files || []);
        } catch (e) {
            document.getElementById('fileListWrap').innerHTML = '<div class="empty">加载失败: ' + e + '</div>';
        }
    }
    function formatBytes(bytes) {
        if (bytes < 1024) return bytes + ' B';
        if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
        if (bytes < 1024*1024*1024) return (bytes/1024/1024).toFixed(1) + ' MB';
        return (bytes/1024/1024/1024).toFixed(2) + ' GB';
    }
    function formatTime(ts) {
        const d = new Date(ts * 1000);
        return d.toLocaleString();
    }
    function renderFiles(files) {
        const wrap = document.getElementById('fileListWrap');
        if (files.length === 0) {
            wrap.innerHTML = '<div class="empty">暂无录像文件</div>';
            return;
        }
        let html = '<table><tr><th>文件名</th><th>大小</th><th>修改时间</th><th>操作</th></tr>';
        files.forEach(f => {
            html += `<tr>
                <td>${f.name}</td>
                <td class="size">${formatBytes(f.size)}</td>
                <td class="mtime">${formatTime(f.mtime)}</td>
                <td>
                    <a class="btn-primary" href="/recordings/${encodeURIComponent(f.name)}" download>下载</a>
                    <button class="btn-danger" onclick="deleteFile('${f.name}')">删除</button>
                </td>
            </tr>`;
        });
        html += '</table>';
        wrap.innerHTML = html;
    }
    async function deleteFile(name) {
        if (!confirm('确定删除 ' + name + ' 吗？')) return;
        try {
            const res = await fetch('/api/recordings/' + encodeURIComponent(name), {method: 'DELETE'});
            const data = await res.json();
            if (data.success) loadFiles(); else alert('删除失败: ' + (data.message || '未知错误'));
        } catch (e) { alert('删除失败: ' + e); }
    }
    loadFiles();
    </script>
</body>
</html>
"""


def _validate_customer_roi(val):
    if not isinstance(val, dict):
        raise ValueError("customer_roi 必须是字典")
    for key in ("x1", "y1", "x2", "y2"):
        if key not in val:
            raise ValueError(f"customer_roi 缺少字段 {key}")
    return val


def _validate_bowl_rois(val):
    if not isinstance(val, list):
        raise ValueError("bowl_rois 必须是列表")
    for item in val:
        if not isinstance(item, dict):
            raise ValueError("bowl_rois 每项必须是字典")
        for key in ("id", "x1", "y1", "x2", "y2"):
            if key not in item:
                raise ValueError(f"bowl_rois 每项缺少字段 {key}")
    return val


def create_app(config_path: str = "config.json", app_state=None, recorder=None, config=None, latest_jpeg=None):
    app = Flask(__name__)
    if config is None:
        config = Config(config_path)

    @app.route("/")
    def index():
        msgs = config.get("audio.messages", {})
        return render_template_string(
            CONFIG_PAGE,
            confidence=config.get("vision.confidence_threshold", 0.5),
            vote_frames=config.get("vision.vote_frames", 5),
            vote_threshold=config.get("vision.vote_threshold", 4),
            debounce=config.get("vision.debounce_seconds", 2.0),
            llm_enabled=config.get("llm.enabled", False),
            msg_customer=msgs.get("customer_approach", "请拿碗放在碗托上"),
            msg_bowl_placed=msgs.get("bowl_placed", "已检测到放碗"),
            msg_meal_ready=msgs.get("meal_ready", "您的餐已准备好，请取餐"),
            msg_bowl_removed=msgs.get("bowl_removed", "碗已取走，请慢用"),
        )

    @app.route("/monitor")
    def monitor():
        return render_template_string(
            MONITOR_PAGE,
            width=config.get("camera.width", 1280),
            height=config.get("camera.height", 720),
        )

    @app.route("/recordings")
    def recordings_page():
        return render_template_string(RECORDINGS_PAGE)

    @app.route("/video_feed")
    def video_feed():
        if latest_jpeg is None:
            return jsonify({"error": "video feed not available"}), 503

        def generate():
            while True:
                frame = latest_jpeg()
                if frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                else:
                    time.sleep(0.05)

        return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

    @app.route("/api/status")
    def api_status():
        if app_state is None:
            return jsonify({"error": "app_state not available"}), 503
        import copy
        with app_state.get("_lock", type("DummyLock", (), {"__enter__": lambda s: s, "__exit__": lambda *a: None})()):
            data = {k: v for k, v in app_state.items() if not k.startswith("_")}
            data["detections"] = copy.deepcopy(data.get("detections", []))
        return jsonify(data)

    @app.route("/api/recording", methods=["POST"])
    def api_recording():
        try:
            data = request.get_json(force=True)
            enabled = bool(data.get("enabled", True))
            if recorder is not None:
                recorder.enabled = enabled
                if not enabled and recorder.is_recording():
                    recorder.stop()
            config.set("video.record_enabled", enabled)
            config.save()
            logger.info(f"录像开关已设置: enabled={enabled}")
            return jsonify({"success": True, "enabled": enabled})
        except Exception as e:
            logger.error(f"录像开关切换失败: {e}")
            return jsonify({"success": False, "message": str(e)}), 400

    @app.route("/api/recordings")
    def api_recordings():
        if recorder is None:
            return jsonify({"files": []})
        files = recorder.list_recordings()
        return jsonify({"files": files})

    @app.route("/api/recordings/<path:name>", methods=["DELETE"])
    def api_delete_recording(name):
        if recorder is None:
            return jsonify({"success": False, "message": "recorder not available"}), 503
        ok = recorder.delete_recording(name)
        return jsonify({"success": ok})

    @app.route("/recordings/<path:name>")
    def download_recording(name):
        if recorder is None:
            return jsonify({"error": "recorder not available"}), 503
        safe_path = (recorder.record_dir / name).resolve()
        try:
            safe_path.relative_to(recorder.record_dir.resolve())
        except ValueError:
            return jsonify({"error": "invalid path"}), 403
        if not safe_path.exists():
            return jsonify({"error": "file not found"}), 404
        return send_from_directory(str(recorder.record_dir), name, as_attachment=True)

    @app.route("/api/config", methods=["POST"])
    def update_config():
        try:
            data = request.get_json(force=True)
            if "customer_roi" in data:
                roi = _validate_customer_roi(json.loads(data["customer_roi"]))
                config.set("vision.customer_roi", roi)
            if "bowl_rois" in data:
                rois = _validate_bowl_rois(json.loads(data["bowl_rois"]))
                config.set("vision.bowl_rois", rois)
            if "confidence" in data:
                config.set("vision.confidence_threshold", data["confidence"])
            if "vote_frames" in data:
                config.set("vision.vote_frames", data["vote_frames"])
            if "vote_threshold" in data:
                config.set("vision.vote_threshold", data["vote_threshold"])
            if "debounce" in data:
                config.set("vision.debounce_seconds", data["debounce"])
            if "llm_enabled" in data:
                config.set("llm.enabled", data["llm_enabled"])
            if "messages" in data:
                msgs = data["messages"]
                if isinstance(msgs, dict):
                    config.set("audio.messages", msgs)
            config.save()
            logger.info("配置已更新并保存")
            return jsonify({"success": True, "message": "配置保存成功"})
        except Exception as e:
            logger.error(f"配置更新失败: {e}")
            return jsonify({"success": False, "message": str(e)}), 400

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify(config.data)

    return app


def run_server(host: str = "0.0.0.0", port: int = 8080, config_path: str = "config.json"):
    app = create_app(config_path)
    logger.info(f"配置服务启动于 http://{host}:{port}")
    app.run(host=host, port=port, threaded=True)
