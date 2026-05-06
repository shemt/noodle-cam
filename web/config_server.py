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
        h3 {
            padding: 10px 14px;
            border-radius: 6px;
            margin-top: 22px;
            margin-bottom: 10px;
            font-size: 15px;
            font-weight: bold;
            border-left: 5px solid;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        h3:nth-of-type(1) { background: #e3f2fd; color: #0d47a1; border-left-color: #1565c0; }
        h3:nth-of-type(2) { background: #f3e5f5; color: #4a148c; border-left-color: #7b1fa2; }
        h3:nth-of-type(3) { background: #e8f5e9; color: #1b5e20; border-left-color: #388e3c; }
        h3:nth-of-type(4) { background: #fff3e0; color: #bf360c; border-left-color: #f57c00; }
        h3:nth-of-type(5) { background: #fce4ec; color: #880e4f; border-left-color: #c2185b; }
        h3:nth-of-type(6) { background: #e0f2f1; color: #004d40; border-left-color: #00796b; }
        h3:nth-of-type(7) { background: #f5f5f5; color: #212121; border-left-color: #616161; }
        /* 分类内容缩进 */
        label { margin-left: 12px; }
        input, select { margin-left: 12px; width: calc(100% - 12px) !important; }
        .hint { font-size: 11px; color: #888; font-weight: normal; margin-left: 4px; }
    </style>
</head>
<body>
    """ + NAV_BAR + """
    <h1>NoodleCam 参数配置</h1>
    <div class="container">
        <div class="panel">
            <h2>配置项</h2>

            <h3>摄像头</h3>
            <label>设备索引 <span class="hint">(需重启生效)</span></label>
            <input type="number" id="cam_index" value="{{ camera_index }}">
            <label>宽度 <span class="hint">(需重启生效)</span></label>
            <input type="number" id="cam_width" value="{{ camera_width }}">
            <label>高度 <span class="hint">(需重启生效)</span></label>
            <input type="number" id="cam_height" value="{{ camera_height }}">
            <label>亮度</label>
            <input type="number" id="cam_brightness" step="1" value="{{ camera_brightness }}">
            <label>对比度</label>
            <input type="number" id="cam_contrast" step="0.1" value="{{ camera_contrast }}">
            <label>饱和度</label>
            <input type="number" id="cam_saturation" step="0.1" value="{{ camera_saturation }}">
            <label>Gamma</label>
            <input type="number" id="cam_gamma" step="0.05" value="{{ camera_gamma }}">

            <h3>视觉检测</h3>
            <label>模型路径 <span class="hint">(需重启生效)</span></label>
            <input type="text" id="vision_model_path" value="{{ vision_model_path }}">
            <label>置信度阈值</label>
            <input type="number" id="vision_confidence" step="0.05" min="0" max="1" value="{{ vision_confidence }}">
            <label>推理间隔帧数 <span class="hint">(需重启生效)</span></label>
            <input type="number" id="vision_inference_interval" value="{{ vision_inference_interval }}">
            <label>多帧投票 N</label>
            <input type="number" id="vision_vote_frames" value="{{ vision_vote_frames }}">
            <label>投票通过 M</label>
            <input type="number" id="vision_vote_threshold" value="{{ vision_vote_threshold }}">
            <label>防抖时间（秒）</label>
            <input type="number" id="vision_debounce" step="0.1" value="{{ vision_debounce }}">

            <h3>音频</h3>
            <label>音量 (0-100)</label>
            <input type="number" id="audio_volume" min="0" max="100" value="{{ audio_volume }}">
            <label>语音角色 <span class="hint">(需重启生效)</span></label>
            <input type="text" id="audio_voice" value="{{ audio_voice }}">
            <label>语速</label>
            <input type="text" id="audio_rate" value="{{ audio_rate }}">
            <label>音频缓存目录 <span class="hint">(需重启生效)</span></label>
            <input type="text" id="audio_dir" value="{{ audio_dir }}">
            <label>客户靠近提示语</label>
            <input type="text" id="msg_customer" value="{{ msg_customer }}">
            <label>放碗检测提示语</label>
            <input type="text" id="msg_bowl_placed" value="{{ msg_bowl_placed }}">
            <label>餐品就绪提示语</label>
            <input type="text" id="msg_meal_ready" value="{{ msg_meal_ready }}">
            <label>取碗完成提示语</label>
            <input type="text" id="msg_bowl_removed" value="{{ msg_bowl_removed }}">

            <h3>后端</h3>
            <label>URL</label>
            <input type="text" id="backend_url" value="{{ backend_url }}">
            <label>心跳间隔（秒）</label>
            <input type="number" id="backend_heartbeat" value="{{ backend_heartbeat }}">

            <h3>视频</h3>
            <label>RTSP 推流 <span class="hint">(需重启生效)</span></label>
            <select id="video_rtsp_enabled">
                <option value="true" {{ 'selected' if video_rtsp_enabled else '' }}>启用</option>
                <option value="false" {{ 'selected' if not video_rtsp_enabled else '' }}>禁用</option>
            </select>
            <label>RTSP FPS <span class="hint">(需重启生效)</span></label>
            <input type="number" id="video_rtsp_fps" value="{{ video_rtsp_fps }}">
            <label>RTSP 端口 <span class="hint">(需重启生效)</span></label>
            <input type="number" id="video_rtsp_port" value="{{ video_rtsp_port }}">
            <label>RTSP 码率</label>
            <input type="number" id="video_rtsp_bitrate" value="{{ video_rtsp_bitrate }}">
            <label>录像开关</label>
            <select id="video_record_enabled">
                <option value="true" {{ 'selected' if video_record_enabled else '' }}>启用</option>
                <option value="false" {{ 'selected' if not video_record_enabled else '' }}>禁用</option>
            </select>
            <label>录像目录 <span class="hint">(需重启生效)</span></label>
            <input type="text" id="video_record_dir" value="{{ video_record_dir }}">
            <label>最大存储空间 (GB) <span class="hint">(需重启生效)</span></label>
            <input type="number" id="video_max_storage" value="{{ video_max_storage }}">

            <h3>Web 服务</h3>
            <label>绑定地址 <span class="hint">(需重启生效)</span></label>
            <input type="text" id="web_host" value="{{ web_host }}">
            <label>端口 <span class="hint">(需重启生效)</span></label>
            <input type="number" id="web_port" value="{{ web_port }}">

            <h3>LLM</h3>
            <label>启用 LLM 备用</label>
            <select id="llm_enabled">
                <option value="false" {{ 'selected' if not llm_enabled else '' }}>禁用</option>
                <option value="true" {{ 'selected' if llm_enabled else '' }}>启用</option>
            </select>
            <label>API Key</label>
            <input type="text" id="llm_api_key" value="{{ llm_api_key }}">
            <label>Fallback 阈值</label>
            <input type="number" id="llm_fallback" step="0.05" min="0" max="1" value="{{ llm_fallback }}">
            <label>模型</label>
            <input type="text" id="llm_model" value="{{ llm_model }}">

            <div style="margin-top:20px;">
                <button class="btn-primary" onclick="saveConfig()">保存配置</button>
            </div>
            <div id="msg"></div>
        </div>

        <div class="panel">
            <h2>配置 JSON 预览</h2>
            <textarea id="configPreview" rows="30" readonly style="font-family:monospace;font-size:12px;"></textarea>
        </div>
    </div>

    <script>
    function getValue(id, type) {
        const el = document.getElementById(id);
        if (!el) return null;
        if (type === 'bool') return el.value === 'true';
        if (type === 'int') return parseInt(el.value);
        if (type === 'float') return parseFloat(el.value);
        return el.value;
    }
    function buildPayload() {
        return {
            camera: {
                index: getValue('cam_index', 'int'),
                width: getValue('cam_width', 'int'),
                height: getValue('cam_height', 'int'),
                brightness: getValue('cam_brightness', 'int'),
                contrast: getValue('cam_contrast', 'float'),
                saturation: getValue('cam_saturation', 'float'),
                gamma: getValue('cam_gamma', 'float'),
            },
            vision: {
                model_path: getValue('vision_model_path'),
                confidence_threshold: getValue('vision_confidence', 'float'),
                inference_interval: getValue('vision_inference_interval', 'int'),
                vote_frames: getValue('vision_vote_frames', 'int'),
                vote_threshold: getValue('vision_vote_threshold', 'int'),
                debounce_seconds: getValue('vision_debounce', 'float'),
            },
            audio: {
                volume: getValue('audio_volume', 'int'),
                voice: getValue('audio_voice'),
                rate: getValue('audio_rate'),
                audio_dir: getValue('audio_dir'),
                messages: {
                    customer_approach: getValue('msg_customer'),
                    bowl_placed: getValue('msg_bowl_placed'),
                    meal_ready: getValue('msg_meal_ready'),
                    bowl_removed: getValue('msg_bowl_removed'),
                }
            },
            backend: {
                url: getValue('backend_url'),
                heartbeat_interval: getValue('backend_heartbeat', 'int'),
            },
            video: {
                rtsp_enabled: getValue('video_rtsp_enabled', 'bool'),
                rtsp_fps: getValue('video_rtsp_fps', 'int'),
                rtsp_port: getValue('video_rtsp_port', 'int'),
                rtsp_bitrate: getValue('video_rtsp_bitrate', 'int'),
                record_enabled: getValue('video_record_enabled', 'bool'),
                record_dir: getValue('video_record_dir'),
                max_storage_gb: getValue('video_max_storage', 'int'),
            },
            web: {
                host: getValue('web_host'),
                port: getValue('web_port', 'int'),
            },
            llm: {
                enabled: getValue('llm_enabled', 'bool'),
                api_key: getValue('llm_api_key'),
                fallback_threshold: getValue('llm_fallback', 'float'),
                model: getValue('llm_model'),
            }
        };
    }
    function updatePreview() {
        document.getElementById('configPreview').value = JSON.stringify(buildPayload(), null, 2);
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
    document.querySelectorAll('input, select').forEach(el => {
        el.addEventListener('change', updatePreview);
        el.addEventListener('input', updatePreview);
    });
    updatePreview();
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
        .stat-card.bowl-yes { border-left-color: #28a745; }
        .stat-card.bowl-no { border-left-color: #6c757d; }
        .stat-value { font-size: 20px; font-weight: bold; color: #333; }
        .stat-label { font-size: 11px; color: #666; margin-top: 2px; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 13px; }
        th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }
        th { background: #f8f9fa; }
        .empty { color: #999; padding: 16px; text-align: center; }
        .btn-primary { background: #007bff; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .btn-danger { background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .btn-secondary { background: #6c757d; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .btn-success { background: #28a745; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .btn-warning { background: #fd7e14; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .mode-active { background: #28a745 !important; color: white !important; border-color: #28a745 !important; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }
        .badge-person { background: #d4edda; color: #155724; }
        .badge-bowl { background: #fff3cd; color: #856404; }
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
                    <img id="videoFeed" src="/video_feed?t=init" alt="实时视频流">
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
                        <div class="stat-value" id="customerVal">--</div>
                        <div class="stat-label">客户检测</div>
                    </div>
                    <div class="stat-card" id="bowlCard">
                        <div class="stat-value" id="bowlVal">--</div>
                        <div class="stat-label">碗状态</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" id="fpsVal">--</div>
                        <div class="stat-label">FPS</div>
                    </div>
                    <div class="stat-card" id="recCard">
                        <div class="stat-value" id="recVal">--</div>
                        <div class="stat-label">录像</div>
                    </div>
                </div>
                <div style="margin-top:12px;">
                    <button id="recToggle" class="btn-primary" onclick="toggleRecording()">加载中...</button>
                </div>
            </div>

            <div class="section">
                <h2>调试模拟</h2>
                <div style="display:flex;flex-wrap:wrap;gap:6px;">
                    <button class="btn-success" onclick="simulateBowl(true)">仿真碗存在</button>
                    <button class="btn-warning" onclick="simulateBowl(false)">仿真碗不存在</button>
                    <button class="btn-secondary" onclick="simulateBowl(null)">清除仿真</button>
                </div>
                <div id="simMsg" style="margin-top:6px;font-size:12px;min-height:18px;"></div>
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

    // ========== Video Feed Robust Reconnection ==========
    const videoImg = document.getElementById('videoFeed');
    let vfErrorCount = 0;
    let vfRetryTimer = null;
    let vfHealthTimer = null;
    const VF_MAX_RETRY = 10;
    const VF_RETRY_BASE_MS = 800;

    function vfSetSrc() {
        const ts = Date.now();
        videoImg.src = '/video_feed?t=' + ts;
    }

    function vfScheduleRetry() {
        if (vfRetryTimer) clearTimeout(vfRetryTimer);
        if (vfErrorCount >= VF_MAX_RETRY) {
            console.warn('视频流重试次数耗尽，停止自动重连');
            return;
        }
        const delay = Math.min(VF_RETRY_BASE_MS * Math.pow(1.5, vfErrorCount), 8000);
        vfErrorCount++;
        vfRetryTimer = setTimeout(() => {
            console.log('视频流重试 #' + vfErrorCount + ' 延迟 ' + delay + 'ms');
            vfSetSrc();
        }, delay);
    }

    videoImg.addEventListener('error', () => {
        console.error('videoFeed error event');
        vfScheduleRetry();
    });

    videoImg.addEventListener('load', () => {
        if (vfErrorCount > 0) {
            console.log('视频流恢复');
            vfErrorCount = 0;
        }
    });

    // 页面可见性变化时：隐藏暂停、显示刷新
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible') {
            console.log('页面重新可见，刷新视频流');
            vfErrorCount = 0;
            if (vfRetryTimer) clearTimeout(vfRetryTimer);
            vfSetSrc();
        }
    });

    // 健康检查：如果图片完成加载但宽度为0，说明加载失败
    function vfHealthCheck() {
        if (document.visibilityState !== 'visible') return;
        if (videoImg.complete && videoImg.naturalWidth === 0) {
            console.warn('健康检查发现视频流已中断');
            vfScheduleRetry();
        }
    }
    vfHealthTimer = setInterval(vfHealthCheck, 3000);

    // ========== Status polling ==========
    let lastRecordEnabled = null;
    async function fetchStatus() {
        try {
            const res = await fetch('/api/status');
            updateUI(await res.json());
        } catch (e) { console.error('状态获取失败:', e); }
    }
    function updateUI(data) {
        document.getElementById('customerVal').textContent = data.customer_detected ? '检测到' : '未检测';
        document.getElementById('customerVal').style.color = data.customer_detected ? '#28a745' : '#666';
        const anyBowl = data.any_bowl_present;
        const bowlSim = data.bowl_simulated;
        document.getElementById('bowlVal').textContent = anyBowl ? '有碗' : '无碗';
        if (bowlSim) document.getElementById('bowlVal').textContent += ' [仿真]';
        document.getElementById('bowlCard').className = 'stat-card ' + (anyBowl ? 'bowl-yes' : 'bowl-no');
        document.getElementById('fpsVal').textContent = data.fps || 0;
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
    async function simulateBowl(present) {
        try {
            const res = await fetch('/api/simulate', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({bowl_present: present})
            });
            const data = await res.json();
            const el = document.getElementById('simMsg');
            el.textContent = data.message || data.error || '已发送';
            el.style.color = data.success ? '#28a745' : '#dc3545';
            setTimeout(() => { el.textContent = ''; }, 3000);
        } catch (e) {
            document.getElementById('simMsg').textContent = '请求失败: ' + e;
        }
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
        .btn-success { background: #28a745; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .btn-danger { background: #dc3545; color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-size: 13px; }
        .empty { color: #999; padding: 30px; text-align: center; }
        .size { color: #666; font-family: monospace; }
        .mtime { color: #666; font-size: 13px; }
        .video-row { background: #f8f9fa; }
        .video-row td { padding: 0; border: none; }
        video { width: 100%; max-height: 400px; background: #000; }
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
    let expandedFile = null;
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
    function togglePlay(name) {
        const row = document.getElementById('video-row-' + name);
        if (!row) return;
        if (expandedFile === name) {
            row.style.display = 'none';
            expandedFile = null;
        } else {
            // hide previous
            if (expandedFile) {
                const prev = document.getElementById('video-row-' + expandedFile);
                if (prev) prev.style.display = 'none';
            }
            const video = row.querySelector('video');
            if (video) video.src = '/recordings/' + encodeURIComponent(name);
            row.style.display = 'table-row';
            expandedFile = name;
        }
    }
    function renderFiles(files) {
        const wrap = document.getElementById('fileListWrap');
        if (files.length === 0) {
            wrap.innerHTML = '<div class="empty">暂无录像文件</div>';
            return;
        }
        let html = '<table><tr><th>文件名</th><th>大小</th><th>修改时间</th><th>操作</th></tr>';
        files.forEach(f => {
            const encName = encodeURIComponent(f.name).replace(/'/g, "%27");
            html += `<tr>
                <td>${f.name}</td>
                <td class="size">${formatBytes(f.size)}</td>
                <td class="mtime">${formatTime(f.mtime)}</td>
                <td>
                    <button class="btn-success" onclick="togglePlay('${encName}')">播放</button>
                    <a class="btn-primary" href="/recordings/${encName}?download=1" download>下载</a>
                    <button class="btn-danger" onclick="deleteFile('${encName}')">删除</button>
                </td>
            </tr>`;
            html += `<tr class="video-row" id="video-row-${encName}" style="display:none;">
                <td colspan="4">
                    <video controls preload="none"></video>
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


def create_app(config_path: str = "config.json", app_state=None, recorder=None, config=None, latest_jpeg=None, app_instance=None):
    app = Flask(__name__)
    if config is None:
        config = Config(config_path)

    @app.route("/")
    def index():
        msgs = config.get("audio.messages", {})
        return render_template_string(
            CONFIG_PAGE,
            camera_index=config.get("camera.index", 0),
            camera_width=config.get("camera.width", 1280),
            camera_height=config.get("camera.height", 720),
            camera_brightness=config.get("camera.brightness", 30),
            camera_contrast=config.get("camera.contrast", 1.2),
            camera_saturation=config.get("camera.saturation", 1.2),
            camera_gamma=config.get("camera.gamma", 0.85),
            vision_model_path=config.get("vision.model_path", "models/yolov5s.onnx"),
            vision_confidence=config.get("vision.confidence_threshold", 0.5),
            vision_inference_interval=config.get("vision.inference_interval", 1),
            vision_vote_frames=config.get("vision.vote_frames", 5),
            vision_vote_threshold=config.get("vision.vote_threshold", 4),
            vision_debounce=config.get("vision.debounce_seconds", 2.0),
            audio_volume=config.get("audio.volume", 80),
            audio_voice=config.get("audio.voice", "zh-CN-XiaoxiaoNeural"),
            audio_rate=config.get("audio.rate", "-15%"),
            audio_dir=config.get("audio.audio_dir", "audio_clips"),
            msg_customer=msgs.get("customer_approach", "请拿碗放在碗托上"),
            msg_bowl_placed=msgs.get("bowl_placed", "已检测到放碗"),
            msg_meal_ready=msgs.get("meal_ready", "您的餐已准备好，请取餐"),
            msg_bowl_removed=msgs.get("bowl_removed", "碗已取走，请慢用"),
            backend_url=config.get("backend.url", "http://localhost:5000"),
            backend_heartbeat=config.get("backend.heartbeat_interval", 86400),
            video_rtsp_enabled=config.get("video.rtsp_enabled", True),
            video_rtsp_fps=config.get("video.rtsp_fps", 15),
            video_rtsp_port=config.get("video.rtsp_port", 8554),
            video_rtsp_bitrate=config.get("video.rtsp_bitrate", 500),
            video_record_enabled=config.get("video.record_enabled", True),
            video_record_dir=config.get("video.record_dir", "recordings"),
            video_max_storage=config.get("video.max_storage_gb", 2),
            web_host=config.get("web.host", "0.0.0.0"),
            web_port=config.get("web.port", 8090),
            llm_enabled=config.get("llm.enabled", False),
            llm_api_key=config.get("llm.api_key", ""),
            llm_fallback=config.get("llm.fallback_threshold", 0.3),
            llm_model=config.get("llm.model", "qwen-vl-plus"),
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

    # 1x1 透明 GIF，作为无帧时的 keep-alive 占位
    _BLANK_GIF = bytes([
        0x47, 0x49, 0x46, 0x38, 0x39, 0x61, 0x01, 0x00, 0x01, 0x00,
        0x80, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x2C,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0x02,
        0x02, 0x44, 0x01, 0x00, 0x3B,
    ])

    @app.route("/video_feed")
    def video_feed():
        if latest_jpeg is None:
            return jsonify({"error": "video feed not available"}), 503

        def generate():
            try:
                while True:
                    frame = latest_jpeg()
                    if frame:
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                    else:
                        # 无帧时发送 1x1 透明 GIF 保持连接存活
                        yield (b'--frame\r\n'
                               b'Content-Type: image/gif\r\n\r\n'
                               + create_app._BLANK_GIF + b'\r\n')
                        time.sleep(0.1)
                    time.sleep(0.18)  # ~5 fps
            except (GeneratorExit, BrokenPipeError, ConnectionResetError, OSError):
                pass  # 客户端断开，优雅退出
            finally:
                logger.debug("video_feed 生成器退出")

        resp = Response(
            generate(),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            direct_passthrough=False,
        )
        # MJPEG 流需要持久连接，不能设置 Connection: close
        resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        resp.headers['Pragma'] = 'no-cache'
        resp.headers['Expires'] = '0'
        resp.headers['X-Accel-Buffering'] = 'no'  # 禁用 Nginx 等代理缓冲
        return resp

    @app.route("/api/status")
    def api_status():
        if app_state is None:
            return jsonify({"error": "app_state not available"}), 503
        import copy
        with app_state.get("_lock", type("DummyLock", (), {"__enter__": lambda s: s, "__exit__": lambda *a: None})()):
            data = {k: v for k, v in app_state.items() if not k.startswith("_")}
            data["detections"] = copy.deepcopy(data.get("detections", []))
            data["bowl_simulated"] = app_instance.simulate_bowl_override is not None if app_instance else False
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

    @app.route("/api/simulate", methods=["POST"])
    def api_simulate():
        if app_instance is None:
            return jsonify({"success": False, "error": "app instance not available"}), 503
        try:
            data = request.get_json(force=True)
            bowl_present = data.get("bowl_present")
            if bowl_present is None:
                app_instance.simulate_bowl_override = None
                msg = "已清除仿真"
            elif bowl_present is True:
                app_instance.simulate_bowl_override = True
                msg = "已设置仿真：碗存在"
            elif bowl_present is False:
                app_instance.simulate_bowl_override = False
                msg = "已设置仿真：碗不存在"
            else:
                return jsonify({"success": False, "error": f"无效值: {bowl_present}"}), 400
            logger.info(f"仿真设置: bowl_present={bowl_present}")
            return jsonify({"success": True, "message": msg})
        except Exception as e:
            logger.error(f"模拟事件失败: {e}")
            return jsonify({"success": False, "error": str(e)}), 400

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
        as_attachment = request.args.get("download", "0") == "1"
        return send_from_directory(str(recorder.record_dir.resolve()), name, as_attachment=as_attachment)

    @app.route("/api/config", methods=["POST"])
    def update_config():
        try:
            data = request.get_json(force=True)
            # 处理嵌套对象形式的完整配置
            if "camera" in data and isinstance(data["camera"], dict):
                cam = data["camera"]
                for k, v in cam.items():
                    config.set(f"camera.{k}", v)
            if "vision" in data and isinstance(data["vision"], dict):
                vis = data["vision"]
                for k, v in vis.items():
                    config.set(f"vision.{k}", v)
            if "audio" in data and isinstance(data["audio"], dict):
                aud = data["audio"]
                for k, v in aud.items():
                    if k == "messages" and isinstance(v, dict):
                        config.set("audio.messages", v)
                    else:
                        config.set(f"audio.{k}", v)
            if "backend" in data and isinstance(data["backend"], dict):
                be = data["backend"]
                for k, v in be.items():
                    config.set(f"backend.{k}", v)
            if "video" in data and isinstance(data["video"], dict):
                vid = data["video"]
                for k, v in vid.items():
                    config.set(f"video.{k}", v)
                # 实时更新录像开关
                if "record_enabled" in vid and recorder is not None:
                    recorder.enabled = bool(vid["record_enabled"])
                    if not recorder.enabled and recorder.is_recording():
                        recorder.stop()
            if "web" in data and isinstance(data["web"], dict):
                web = data["web"]
                for k, v in web.items():
                    config.set(f"web.{k}", v)
            if "llm" in data and isinstance(data["llm"], dict):
                llm = data["llm"]
                for k, v in llm.items():
                    config.set(f"llm.{k}", v)

            # 兼容旧版扁平格式（ROI 等）
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
