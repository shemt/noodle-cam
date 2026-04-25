import json
import logging
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string

from config.settings import Config

logger = logging.getLogger(__name__)

HTML_PAGE = """
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
        .canvas-wrap {
            position: relative; display: inline-block; border: 1px solid #ccc;
            background: #1a1a2e; overflow: hidden;
        }
        canvas { display: block; cursor: crosshair; }
        .overlay-label {
            position: absolute; top: 4px; left: 4px; color: #0f0;
            font-size: 12px; background: rgba(0,0,0,0.6); padding: 2px 6px; border-radius: 3px;
        }
        label { display: block; margin: 10px 0 4px; font-weight: bold; }
        input, select, textarea { width: 100%; padding: 8px; box-sizing: border-box; }
        button { padding: 8px 16px; margin: 4px 4px 4px 0; cursor: pointer; border-radius: 4px; border: 1px solid #ccc; }
        .btn-primary { background: #007bff; color: white; border: none; }
        .btn-danger { background: #dc3545; color: white; border: none; }
        .btn-secondary { background: #6c757d; color: white; border: none; }
        .success { color: green; }
        .error { color: red; }
        .roi-tag {
            display: inline-block; padding: 4px 10px; margin: 4px 4px 0 0;
            border-radius: 4px; font-size: 13px; background: #e9ecef; border: 1px solid #dee2e6;
        }
        .roi-tag .del { color: #dc3545; cursor: pointer; margin-left: 8px; font-weight: bold; }
        .mode-active { background: #28a745 !important; color: white !important; border-color: #28a745 !important; }
        #msg { margin-top: 10px; font-weight: bold; }
        .info { color: #666; font-size: 13px; margin-top: 4px; }
        table { width: 100%; border-collapse: collapse; margin-top: 8px; font-size: 13px; }
        th, td { border: 1px solid #ddd; padding: 6px; text-align: left; }
        th { background: #f8f9fa; }
    </style>
</head>
<body>
    <h1>NoodleCam 配置界面</h1>
    <div class="container">
        <div class="panel">
            <h2>ROI 区域设定（鼠标框选）</h2>
            <p class="info">
                分辨率: <span id="resLabel">{{ width }}x{{ height }}</span> |
                鼠标拖拽框选区域，完成后保存
            </p>
            <div>
                <button id="btnCustomer" class="mode-active" onclick="setMode('customer')">客户检测区</button>
                <button id="btnBowl" onclick="setMode('bowl')">碗位检测区</button>
                <button class="btn-secondary" onclick="clearAll()">清空全部</button>
            </div>
            <div class="canvas-wrap" id="canvasWrap">
                <canvas id="roiCanvas" width="{{ width }}" height="{{ height }}"></canvas>
                <div class="overlay-label">当前模式: <span id="modeLabel">客户检测区</span></div>
            </div>
            <div style="margin-top:10px;">
                <label>已设定区域</label>
                <div id="roiList"></div>
            </div>
            <div style="margin-top:10px;">
                <label>底图（可选，输入图片 URL 或 base64）</label>
                <input type="text" id="bgImageUrl" placeholder="留空使用网格底图">
                <button onclick="loadBgImage()">加载</button>
            </div>
        </div>

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

            <h2 style="margin-top:20px;">配置 JSON</h2>
            <textarea id="configPreview" rows="10" readonly></textarea>
            <div style="margin-top:10px;">
                <button class="btn-primary" onclick="saveConfig()">保存配置</button>
            </div>
            <div id="msg"></div>
        </div>
    </div>

    <script>
    const canvas = document.getElementById('roiCanvas');
    const ctx = canvas.getContext('2d');
    const wrap = document.getElementById('canvasWrap');
    let mode = 'customer'; // 'customer' or 'bowl'
    let isDrawing = false;
    let startX = 0, startY = 0;
    let currentRect = null;
    let customerRoi = null; // {x1,y1,x2,y2}
    let bowlRois = [];      // [{id,x1,y1,x2,y2},...]
    let bgImage = null;

    // 缩放系数：canvas 逻辑尺寸 vs 显示尺寸
    let scaleX = 1, scaleY = 1;

    function updateScale() {
        const rect = canvas.getBoundingClientRect();
        scaleX = canvas.width / rect.width;
        scaleY = canvas.height / rect.height;
    }

    function drawGrid() {
        if (bgImage) {
            ctx.drawImage(bgImage, 0, 0, canvas.width, canvas.height);
        } else {
            ctx.fillStyle = '#1a1a2e';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            ctx.strokeStyle = '#333';
            ctx.lineWidth = 1;
            const step = 50;
            for (let x = 0; x <= canvas.width; x += step) {
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, canvas.height); ctx.stroke();
            }
            for (let y = 0; y <= canvas.height; y += step) {
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
            }
            // 坐标标签
            ctx.fillStyle = '#666';
            ctx.font = '10px monospace';
            for (let x = 0; x <= canvas.width; x += step) {
                ctx.fillText(x, x + 2, canvas.height - 2);
            }
            for (let y = 0; y <= canvas.height; y += step) {
                ctx.fillText(y, 2, y - 2);
            }
        }
    }

    function drawRoi(roi, color, label) {
        const {x1, y1, x2, y2} = roi;
        ctx.strokeStyle = color;
        ctx.lineWidth = 3;
        ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
        ctx.fillStyle = color;
        ctx.font = 'bold 14px sans-serif';
        ctx.fillText(label, x1 + 4, y1 + 18);
        // 半透明填充
        ctx.fillStyle = color.replace(')', ', 0.15)').replace('rgb', 'rgba');
        ctx.fillRect(x1, y1, x2 - x1, y2 - y1);
    }

    function redraw() {
        drawGrid();
        if (customerRoi) drawRoi(customerRoi, 'rgb(0, 200, 0)', '客户区');
        bowlRois.forEach(r => drawRoi(r, 'rgb(255, 165, 0)', '碗位#' + r.id));
        if (currentRect) drawRoi(currentRect, 'rgb(0, 150, 255)', '框选中');
        updateRoiList();
        updatePreview();
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
        return {
            x: Math.round((e.clientX - rect.left) * scaleX),
            y: Math.round((e.clientY - rect.top) * scaleY)
        };
    }

    canvas.addEventListener('mousedown', e => {
        const pos = getMousePos(e);
        startX = pos.x;
        startY = pos.y;
        isDrawing = true;
        currentRect = {x1: startX, y1: startY, x2: startX, y2: startY};
        redraw();
    });

    canvas.addEventListener('mousemove', e => {
        if (!isDrawing) return;
        const pos = getMousePos(e);
        currentRect = {
            x1: Math.min(startX, pos.x),
            y1: Math.min(startY, pos.y),
            x2: Math.max(startX, pos.x),
            y2: Math.max(startY, pos.y)
        };
        redraw();
    });

    canvas.addEventListener('mouseup', e => {
        if (!isDrawing) return;
        isDrawing = false;
        const pos = getMousePos(e);
        const rect = {
            x1: Math.min(startX, pos.x),
            y1: Math.min(startY, pos.y),
            x2: Math.max(startX, pos.x),
            y2: Math.max(startY, pos.y)
        };
        currentRect = null;

        // 过滤太小的区域
        if (rect.x2 - rect.x1 < 10 || rect.y2 - rect.y1 < 10) {
            redraw();
            return;
        }

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

    canvas.addEventListener('mouseleave', () => {
        if (isDrawing) {
            isDrawing = false;
            currentRect = null;
            redraw();
        }
    });

    function removeBowlRoi(idx) {
        bowlRois.splice(idx, 1);
        redraw();
    }

    function clearAll() {
        if (!confirm('确定清空所有 ROI 设定吗？')) return;
        customerRoi = null;
        bowlRois = [];
        redraw();
    }

    function updateRoiList() {
        const el = document.getElementById('roiList');
        let html = '';
        if (customerRoi) {
            html += `<div class="roi-tag" style="border-color:#28a745;background:#d4edda;">
                客户区: (${customerRoi.x1},${customerRoi.y1})-(${customerRoi.x2},${customerRoi.y2})
                <span class="del" onclick="customerRoi=null;redraw();">&times;</span>
            </div>`;
        }
        bowlRois.forEach((r, i) => {
            html += `<div class="roi-tag" style="border-color:#fd7e14;background:#fff3cd;">
                碗位#${r.id}: (${r.x1},${r.y1})-(${r.x2},${r.y2})
                <span class="del" onclick="removeBowlRoi(${i});redraw();">&times;</span>
            </div>`;
        });
        if (!customerRoi && bowlRois.length === 0) {
            html = '<span style="color:#999;">暂无设定区域，请在左侧画布拖拽框选</span>';
        }
        el.innerHTML = html;
    }

    function updatePreview() {
        const data = buildPayload();
        document.getElementById('configPreview').value = JSON.stringify({
            vision: {
                customer_roi: data.customer_roi,
                bowl_rois: data.bowl_rois,
                confidence_threshold: data.confidence,
                vote_frames: data.vote_frames,
                vote_threshold: data.vote_threshold,
                debounce_seconds: data.debounce
            }
        }, null, 2);
    }

    function buildPayload() {
        return {
            customer_roi: customerRoi ? JSON.stringify(customerRoi) : JSON.stringify({x1:0,y1:0,x2:0,y2:0}),
            bowl_rois: JSON.stringify(bowlRois),
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

    function loadBgImage() {
        const url = document.getElementById('bgImageUrl').value.trim();
        if (!url) { bgImage = null; redraw(); return; }
        const img = new Image();
        img.onload = () => { bgImage = img; redraw(); };
        img.onerror = () => alert('图片加载失败');
        img.src = url;
    }

    // 加载现有配置
    fetch('/api/config').then(r => r.json()).then(cfg => {
        if (cfg.vision && cfg.vision.customer_roi) {
            const cr = cfg.vision.customer_roi;
            if (cr.x2 > cr.x1 && cr.y2 > cr.y1) customerRoi = cr;
        }
        if (cfg.vision && cfg.vision.bowl_rois) {
            bowlRois = cfg.vision.bowl_rois;
        }
        redraw();
    });

    // 响应式缩放 canvas 显示
    function fitCanvas() {
        const maxW = Math.min(wrap.parentElement.clientWidth - 40, canvas.width);
        const ratio = canvas.height / canvas.width;
        wrap.style.width = maxW + 'px';
        wrap.style.height = (maxW * ratio) + 'px';
    }
    window.addEventListener('resize', fitCanvas);
    fitCanvas();
    redraw();
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


def create_app(config_path: str = "config.json"):
    app = Flask(__name__)
    cfg = Config(config_path)

    @app.route("/")
    def index():
        msgs = cfg.get("audio.messages", {})
        return render_template_string(
            HTML_PAGE,
            width=cfg.get("camera.width", 1280),
            height=cfg.get("camera.height", 720),
            confidence=cfg.get("vision.confidence_threshold", 0.5),
            vote_frames=cfg.get("vision.vote_frames", 5),
            vote_threshold=cfg.get("vision.vote_threshold", 4),
            debounce=cfg.get("vision.debounce_seconds", 2.0),
            llm_enabled=cfg.get("llm.enabled", False),
            msg_customer=msgs.get("customer_approach", "请拿碗放在碗托上"),
            msg_bowl_placed=msgs.get("bowl_placed", "已检测到放碗"),
            msg_meal_ready=msgs.get("meal_ready", "您的餐已准备好，请取餐"),
            msg_bowl_removed=msgs.get("bowl_removed", "碗已取走，请慢用"),
        )

    @app.route("/api/config", methods=["POST"])
    def update_config():
        try:
            data = request.get_json(force=True)
            if "customer_roi" in data:
                roi = _validate_customer_roi(json.loads(data["customer_roi"]))
                cfg.set("vision.customer_roi", roi)
            if "bowl_rois" in data:
                rois = _validate_bowl_rois(json.loads(data["bowl_rois"]))
                cfg.set("vision.bowl_rois", rois)
            if "confidence" in data:
                cfg.set("vision.confidence_threshold", data["confidence"])
            if "vote_frames" in data:
                cfg.set("vision.vote_frames", data["vote_frames"])
            if "vote_threshold" in data:
                cfg.set("vision.vote_threshold", data["vote_threshold"])
            if "debounce" in data:
                cfg.set("vision.debounce_seconds", data["debounce"])
            if "llm_enabled" in data:
                cfg.set("llm.enabled", data["llm_enabled"])
            if "messages" in data:
                msgs = data["messages"]
                if isinstance(msgs, dict):
                    cfg.set("audio.messages", msgs)
            cfg.save()
            logger.info("配置已更新并保存")
            return jsonify({"success": True, "message": "配置保存成功"})
        except Exception as e:
            logger.error(f"配置更新失败: {e}")
            return jsonify({"success": False, "message": str(e)}), 400

    @app.route("/api/config", methods=["GET"])
    def get_config():
        return jsonify(cfg.data)

    return app


def run_server(host: str = "0.0.0.0", port: int = 8080, config_path: str = "config.json"):
    app = create_app(config_path)
    logger.info(f"配置服务启动于 http://{host}:{port}")
    app.run(host=host, port=port, threaded=True)
