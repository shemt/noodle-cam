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
        .section { background: #fff; padding: 16px; margin-bottom: 16px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        label { display: block; margin: 8px 0 4px; font-weight: bold; }
        input, select { width: 100%; padding: 8px; box-sizing: border-box; }
        button { padding: 10px 20px; margin-top: 12px; cursor: pointer; }
        .success { color: green; }
        .error { color: red; }
    </style>
</head>
<body>
    <h1>NoodleCam 配置界面</h1>
    <div class="section">
        <h2>ROI 区域设定</h2>
        <label>客户检测区 (x1,y1,x2,y2)</label>
        <input type="text" id="customer_roi" value="{{ customer_roi }}">
        <label>碗位检测区 (JSON 数组)</label>
        <textarea id="bowl_rois" rows="6">{{ bowl_rois }}</textarea>
    </div>
    <div class="section">
        <h2>参数微调</h2>
        <label>YOLO 置信度阈值</label>
        <input type="number" id="confidence" step="0.05" min="0" max="1" value="{{ confidence }}">
        <label>多帧投票 N</label>
        <input type="number" id="vote_frames" value="{{ vote_frames }}">
        <label>投票通过 M</label>
        <input type="number" id="vote_threshold" value="{{ vote_threshold }}">
        <label>防抖时间（秒）</label>
        <input type="number" id="debounce" step="0.1" value="{{ debounce }}">
    </div>
    <div class="section">
        <h2>模式切换</h2>
        <label>工作模式</label>
        <select id="llm_enabled">
            <option value="false" {{ 'selected' if not llm_enabled else '' }}>本地模式</option>
            <option value="true" {{ 'selected' if llm_enabled else '' }}>LLM 备用模式</option>
        </select>
    </div>
    <button onclick="saveConfig()">保存配置</button>
    <div id="msg"></div>
    <script>
        function saveConfig() {
            const data = {
                customer_roi: document.getElementById('customer_roi').value,
                bowl_rois: document.getElementById('bowl_rois').value,
                confidence: parseFloat(document.getElementById('confidence').value),
                vote_frames: parseInt(document.getElementById('vote_frames').value),
                vote_threshold: parseInt(document.getElementById('vote_threshold').value),
                debounce: parseFloat(document.getElementById('debounce').value),
                llm_enabled: document.getElementById('llm_enabled').value === 'true'
            };
            fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            }).then(r => r.json()).then(res => {
                document.getElementById('msg').innerText = res.message;
                document.getElementById('msg').className = res.success ? 'success' : 'error';
            });
        }
    </script>
</body>
</html>
"""


def create_app(config_path: str = "config.json"):
    app = Flask(__name__)
    cfg = Config(config_path)

    @app.route("/")
    def index():
        return render_template_string(
            HTML_PAGE,
            customer_roi=json.dumps(cfg.get("vision.customer_roi", {})),
            bowl_rois=json.dumps(cfg.get("vision.bowl_rois", []), ensure_ascii=False, indent=2),
            confidence=cfg.get("vision.confidence_threshold", 0.5),
            vote_frames=cfg.get("vision.vote_frames", 5),
            vote_threshold=cfg.get("vision.vote_threshold", 4),
            debounce=cfg.get("vision.debounce_seconds", 2.0),
            llm_enabled=cfg.get("llm.enabled", False),
        )

    @app.route("/api/config", methods=["POST"])
    def update_config():
        try:
            data = request.get_json(force=True)
            if "customer_roi" in data:
                cfg.set("vision.customer_roi", json.loads(data["customer_roi"]))
            if "bowl_rois" in data:
                cfg.set("vision.bowl_rois", json.loads(data["bowl_rois"]))
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
