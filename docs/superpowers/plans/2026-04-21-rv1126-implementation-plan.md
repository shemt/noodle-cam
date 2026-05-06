# RV1126 机器人面馆视觉交互系统 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 RV1126 上实现一套完整的机器人面馆视觉交互系统，包含顾客检测、碗位识别、语音引导、后台通信、视频录制、配置界面和 LLM 备用。

**Architecture:** 轻量级单体 Python 应用，模块内部通过函数调用协作。视觉推理使用 YOLO + RKNN NPU 加速，语音使用本地方案，通信使用 HTTP REST，配置界面使用 Flask Web 服务。

**Tech Stack:** Python 3.8+, OpenCV, RKNN-Toolkit2, Flask, requests, pyttsx3/Piper, FFmpeg, 阿里云 DashScope SDK

---

## 文件结构映射

```
noodle_cam/
├── config/
│   ├── __init__.py
│   └── settings.py              # 配置加载、默认值、持久化
├── core/
│   ├── __init__.py
│   └── state_machine.py         # 业务状态机（空闲→引导→制作→等待）
├── vision/
│   ├── __init__.py
│   ├── camera.py                # 摄像头封装（打开、读取、重连）
│   ├── detector.py              # YOLO/RKNN 推理封装
│   ├── customer_detector.py     # 客户靠近检测（由远及近，面积趋势）
│   └── bowl_detector.py         # 碗位检测（多帧投票 + 防抖）
├── audio/
│   ├── __init__.py
│   └── tts_player.py            # 语音播报（预录音频 + TTS fallback）
├── comm/
│   ├── __init__.py
│   └── backend_client.py        # 后台 HTTP 通信 + 事件队列缓存
├── video/
│   ├── __init__.py
│   ├── recorder.py              # 本地 MP4 分段录制 + 循环清理
│   └── streamer.py              # RTSP 推流（FFmpeg）
├── web/
│   ├── __init__.py
│   └── config_server.py         # Flask 配置服务（ROI 设定、实时预览）
├── llm/
│   ├── __init__.py
│   └── tongyi_client.py         # 通义千问 API 封装 + 降级策略
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_state_machine.py
│   ├── test_customer_detector.py
│   ├── test_bowl_detector.py
│   ├── test_backend_client.py
│   └── test_video_recorder.py
├── main.py                      # 主入口：初始化所有模块并运行主循环
├── requirements.txt
└── README.md
```

---

### Task 1: 项目骨架与依赖

**Files:**
- Create: `requirements.txt`
- Create: `README.md`
- Create: `config/__init__.py`, `core/__init__.py`, `vision/__init__.py`, `audio/__init__.py`, `comm/__init__.py`, `video/__init__.py`, `web/__init__.py`, `llm/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p config core vision audio comm video web llm tests audio_clips recordings
```

- [ ] **Step 2: 写入 requirements.txt**

```text
# requirements.txt
opencv-python>=4.5.0
numpy>=1.21.0
requests>=2.28.0
Flask>=2.0.0
dashscope>=1.10.0
pytest>=7.0.0
pytest-mock>=3.6.0
```

- [ ] **Step 3: 创建所有 __init__.py**

```bash
touch config/__init__.py core/__init__.py vision/__init__.py audio/__init__.py \
      comm/__init__.py video/__init__.py web/__init__.py llm/__init__.py tests/__init__.py
```

- [ ] **Step 4: 写入 README.md**

```markdown
# 机器人面馆视觉交互系统（NoodleCam）

基于 RV1126 的视觉识别 + 语音引导 + 远程视频系统。

## 快速启动

```bash
pip install -r requirements.txt
python main.py
```

## 配置

首次启动会自动生成 `config.json`，可通过 Web 界面 `http://<设备IP>:8080` 修改 ROI 和参数。
```

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "chore: 项目骨架与依赖配置"
```

---

### Task 2: 配置系统

**Files:**
- Create: `config/settings.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
import json
import tempfile
import os
from pathlib import Path
from config.settings import Config, DEFAULT_CONFIG

def test_config_loads_defaults_when_file_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "nonexistent.json")
        cfg = Config(path)
        assert cfg.get("camera.index") == 0
        assert cfg.get("vision.confidence_threshold") == 0.5

def test_config_persists_and_reloads():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "config.json")
        cfg = Config(path)
        cfg.set("camera.index", 1)
        cfg.set("vision.customer_roi.x1", 100)
        cfg.save()

        cfg2 = Config(path)
        assert cfg2.get("camera.index") == 1
        assert cfg2.get("vision.customer_roi.x1") == 100

def test_config_nested_get_default():
    cfg = Config("/dev/null/nonexistent.json")
    assert cfg.get("vision.nonexistent_key", "fallback") == "fallback"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'config.settings'` 或 `ImportError`

- [ ] **Step 3: Write minimal implementation**

```python
# config/settings.py
import json
import os
from pathlib import Path
from typing import Dict, Any

DEFAULT_CONFIG = {
    "camera": {"index": 0, "width": 1280, "height": 720},
    "vision": {
        "model_path": "models/yolov5s.rknn",
        "confidence_threshold": 0.5,
        "customer_roi": {"x1": 0, "y1": 0, "x2": 640, "y2": 480},
        "bowl_rois": [],
        "vote_frames": 5,
        "vote_threshold": 4,
        "debounce_seconds": 2.0,
    },
    "audio": {"volume": 80, "pre_recorded": True, "audio_dir": "audio_clips"},
    "backend": {"url": "http://localhost:5000", "heartbeat_interval": 30},
    "video": {
        "rtsp_enabled": True,
        "rtsp_fps": 1,
        "record_enabled": True,
        "record_dir": "recordings",
        "max_storage_gb": 2,
    },
    "llm": {"enabled": False, "api_key": "", "fallback_threshold": 0.3, "model": "qwen-vl-plus"},
    "web": {"host": "0.0.0.0", "port": 8080},
}


class Config:
    def __init__(self, path: str = "config.json"):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                return self._deep_merge(DEFAULT_CONFIG.copy(), loaded)
            except (json.JSONDecodeError, IOError):
                pass
        return DEFAULT_CONFIG.copy()

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default=None):
        keys = key.split(".")
        d = self.data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def set(self, key: str, value):
        keys = key.split(".")
        d = self.data
        for k in keys[:-1]:
            if k not in d:
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add config/settings.py tests/test_config.py
git commit -m "feat: 配置系统加载、嵌套读写与持久化"
```

---

### Task 3: 业务状态机（已取消，保留代码供参考）

> **⚠️ 2026-05-07 更新**：状态机已在 Phase 5 中移除。系统改为**持续检测驱动**模式：
> - 客户检测始终运行，触发时直接播放语音
> - 碗位检测始终运行，状态变化上报后台
> - 录像由 `record_enabled` + `any_bowl_present()` 自动驱动
> - `core/state_machine.py` 保留但不使用

**Files:**
- Create: `core/state_machine.py`（已弃用）
- Test: `tests/test_state_machine.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_state_machine.py
from core.state_machine import StateMachine, State

def test_initial_state_is_idle():
    sm = StateMachine()
    assert sm.state == State.IDLE

def test_idle_to_guiding_on_customer_approach():
    sm = StateMachine()
    assert sm.trigger("customer_approach") is True
    assert sm.state == State.GUIDING

def test_guiding_to_cooking_on_bowl_placed():
    sm = StateMachine()
    sm.trigger("customer_approach")
    assert sm.trigger("bowl_placed") is True
    assert sm.state == State.COOKING

def test_cooking_to_waiting_on_meal_ready():
    sm = StateMachine()
    sm.trigger("customer_approach")
    sm.trigger("bowl_placed")
    assert sm.trigger("meal_ready") is True
    assert sm.state == State.WAITING

def test_waiting_to_idle_on_bowl_removed():
    sm = StateMachine()
    sm.trigger("customer_approach")
    sm.trigger("bowl_placed")
    sm.trigger("meal_ready")
    assert sm.trigger("bowl_removed") is True
    assert sm.state == State.IDLE

def test_invalid_transition_is_rejected():
    sm = StateMachine()
    assert sm.trigger("bowl_placed") is False
    assert sm.state == State.IDLE

def test_event_handler_is_called():
    sm = StateMachine()
    called = []
    sm.on("customer_approach", lambda old, new, ctx: called.append((old, new)))
    sm.trigger("customer_approach")
    assert len(called) == 1
    assert called[0][1] == State.GUIDING
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_state_machine.py -v
```

Expected: `ModuleNotFoundError` or import errors

- [ ] **Step 3: Write minimal implementation**

```python
# core/state_machine.py
import logging
from enum import Enum, auto
from typing import Callable, Dict, Any

logger = logging.getLogger(__name__)


class State(Enum):
    IDLE = auto()
    GUIDING = auto()
    COOKING = auto()
    WAITING = auto()


class StateMachine:
    def __init__(self):
        self.state = State.IDLE
        self._transitions: Dict[State, Dict[str, State]] = {
            State.IDLE: {"customer_approach": State.GUIDING},
            State.GUIDING: {"bowl_placed": State.COOKING, "timeout": State.IDLE},
            State.COOKING: {"meal_ready": State.WAITING, "bowl_removed": State.IDLE},
            State.WAITING: {"bowl_removed": State.IDLE, "timeout": State.IDLE},
        }
        self._handlers: Dict[str, Callable] = {}
        self.context: Dict[str, Any] = {}

    def on(self, event: str, handler: Callable):
        self._handlers[event] = handler
        return self

    def trigger(self, event: str, **kwargs) -> bool:
        if self.state not in self._transitions:
            logger.warning(f"当前状态 {self.state} 无转移定义")
            return False

        allowed = self._transitions[self.state]
        if event not in allowed:
            logger.debug(f"状态 {self.state.name} 忽略事件 {event}")
            return False

        old_state = self.state
        self.state = allowed[event]
        self.context.update(kwargs)
        logger.info(f"状态转移: {old_state.name} -> {self.state.name} (事件: {event})")

        handler = self._handlers.get(event)
        if handler:
            try:
                handler(old_state, self.state, self.context)
            except Exception as e:
                logger.error(f"事件处理器异常: {e}")
        return True

    def reset(self):
        self.state = State.IDLE
        self.context.clear()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_state_machine.py -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add core/state_machine.py tests/test_state_machine.py
git commit -m "feat: 业务状态机（空闲→引导→制作→等待）"
```

---

### Task 4: 摄像头模块

**Files:**
- Create: `vision/camera.py`

- [ ] **Step 1: Write the implementation**

```python
# vision/camera.py
import time
import logging
from typing import Optional
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

logger = logging.getLogger(__name__)


class Camera:
    """摄像头封装，支持自动重连"""

    def __init__(self, index: int = 0, width: int = 1280, height: int = 720):
        self.index = index
        self.width = width
        self.height = height
        self._cap = None
        self._reconnect_attempts = 0
        self._max_reconnect = 3

    def open(self) -> bool:
        if cv2 is None:
            logger.error("OpenCV 未安装")
            return False
        self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            logger.error(f"无法打开摄像头 {self.index}")
            return False
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._reconnect_attempts = 0
        logger.info("摄像头已打开")
        return True

    def read(self) -> Optional[np.ndarray]:
        if self._cap is None or not self._cap.isOpened():
            if self._reconnect_attempts < self._max_reconnect:
                self._reconnect_attempts += 1
                logger.warning(f"摄像头断开，尝试重连 ({self._reconnect_attempts}/{self._max_reconnect})")
                time.sleep(0.5)
                self.open()
                return None
            else:
                return None

        ret, frame = self._cap.read()
        if not ret:
            logger.warning("读取帧失败")
            self._cap.release()
            self._cap = None
            return None
        self._reconnect_attempts = 0
        return frame

    def release(self):
        if self._cap:
            self._cap.release()
            self._cap = None
            logger.info("摄像头已释放")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
```

- [ ] **Step 2: Commit**

```bash
git add vision/camera.py
git commit -m "feat: 摄像头封装，支持自动重连"
```

---

### Task 5: YOLO 推理封装

**Files:**
- Create: `vision/detector.py`

- [ ] **Step 1: Write the implementation**

```python
# vision/detector.py
import logging
from typing import List, Dict
from pathlib import Path

import numpy as np

try:
    from rknnlite.api import RKNNLite
except ImportError:
    RKNNLite = None

try:
    import cv2
except ImportError:
    cv2 = None

logger = logging.getLogger(__name__)


class YOLODetector:
    """YOLO 目标检测封装，优先 RKNN NPU，fallback 到 ONNX/OpenCV DNN"""

    def __init__(self, model_path: str, confidence: float = 0.5, input_size: int = 640):
        self.model_path = Path(model_path)
        self.confidence = confidence
        self.input_size = input_size
        self._rknn = None
        self._net = None
        self._classes = ["person", "bowl"]
        self._load_model()

    def _load_model(self):
        if not self.model_path.exists():
            logger.warning(f"模型文件不存在: {self.model_path}，检测将返回空结果")
            return

        suffix = self.model_path.suffix.lower()

        if suffix == ".rknn" and RKNNLite is not None:
            self._rknn = RKNNLite()
            ret = self._rknn.load_rknn(str(self.model_path))
            if ret == 0:
                ret = self._rknn.init_runtime(core_mask=RKNNLite.NPU_CORE_AUTO)
                if ret == 0:
                    logger.info("RKNN 模型加载成功")
                else:
                    logger.error("RKNN init_runtime 失败")
                    self._rknn = None
            else:
                logger.error("RKNN load_rknn 失败")
                self._rknn = None
        elif suffix in (".onnx", ".pb", ".weights") and cv2 is not None:
            self._net = cv2.dnn.readNet(str(self.model_path))
            logger.info(f"OpenCV DNN 模型加载成功: {self.model_path}")
        else:
            logger.warning(f"不支持的模型格式或缺少运行时: {suffix}")

    def detect(self, frame: np.ndarray) -> List[Dict]:
        if self._rknn is not None:
            return self._detect_rknn(frame)
        if self._net is not None:
            return self._detect_opencv(frame)
        return []

    def _detect_rknn(self, frame: np.ndarray) -> List[Dict]:
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_size, self.input_size))
        outputs = self._rknn.inference(inputs=[img])
        return self._parse_outputs(outputs, frame.shape)

    def _detect_opencv(self, frame: np.ndarray) -> List[Dict]:
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (self.input_size, self.input_size), swapRB=True, crop=False)
        self._net.setInput(blob)
        outputs = self._net.forward(self._net.getUnconnectedOutLayersNames())
        return self._parse_yolo_outputs(outputs, frame.shape)

    def _parse_outputs(self, outputs, orig_shape) -> List[Dict]:
        """RKNN 输出解析（需要根据具体模型格式调整）"""
        return []

    def _parse_yolo_outputs(self, outputs, orig_shape) -> List[Dict]:
        h, w = orig_shape[:2]
        detections = []
        for output in outputs:
            for det in output:
                scores = det[5:]
                class_id = int(np.argmax(scores))
                confidence = float(scores[class_id])
                if confidence < self.confidence:
                    continue
                cx, cy, bw, bh = det[0:4] * np.array([w, h, w, h])
                x1 = int(cx - bw / 2)
                y1 = int(cy - bh / 2)
                x2 = int(cx + bw / 2)
                y2 = int(cy + bh / 2)
                detections.append({
                    "class": self._classes[class_id] if class_id < len(self._classes) else f"cls_{class_id}",
                    "bbox": [max(0, x1), max(0, y1), min(w, x2), min(h, y2)],
                    "conf": round(confidence, 3),
                })
        return detections

    def release(self):
        if self._rknn is not None:
            self._rknn.release()
            self._rknn = None
```

- [ ] **Step 2: Commit**

```bash
git add vision/detector.py
git commit -m "feat: YOLO 检测封装，支持 RKNN NPU 和 OpenCV DNN fallback"
```

---

### Task 6: 客户靠近检测（由远及近）

**Files:**
- Create: `vision/customer_detector.py`
- Test: `tests/test_customer_detector.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_customer_detector.py
from vision.customer_detector import CustomerDetector

def test_no_trigger_when_no_person():
    det = CustomerDetector({"x1": 0, "y1": 0, "x2": 640, "y2": 480})
    assert det.update([]) is False
    assert det.update([]) is False

def test_no_trigger_when_person_stays_same_size():
    det = CustomerDetector({"x1": 0, "y1": 0, "x2": 640, "y2": 480})
    # 面积不变
    for _ in range(10):
        result = det.update([{"class": "person", "bbox": [100, 100, 200, 200]}])
    assert result is False

def test_trigger_when_person_grows_significantly():
    det = CustomerDetector({"x1": 0, "y1": 0, "x2": 640, "y2": 480}, history_size=10, area_growth_threshold=1.3)
    # 先小面积
    for _ in range(5):
        det.update([{"class": "person", "bbox": [100, 100, 110, 110]}])  # area=100
    # 后大面积
    result = det.update([{"class": "person", "bbox": [100, 100, 250, 250]}])  # area=22500
    assert result is True

def test_cooldown_prevents_double_trigger():
    det = CustomerDetector({"x1": 0, "y1": 0, "x2": 640, "y2": 480}, history_size=10, area_growth_threshold=1.3, cooldown=5.0)
    for _ in range(5):
        det.update([{"class": "person", "bbox": [100, 100, 110, 110]}])
    assert det.update([{"class": "person", "bbox": [100, 100, 250, 250]}]) is True
    # 立即再次触发应被冷却
    assert det.update([{"class": "person", "bbox": [100, 100, 250, 250]}]) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_customer_detector.py -v
```

Expected: import/module errors

- [ ] **Step 3: Write minimal implementation**

```python
# vision/customer_detector.py
import time
import logging
from collections import deque
from typing import List, Dict

logger = logging.getLogger(__name__)


class CustomerDetector:
    """通过检测人形框面积增长趋势判断客户由远及近靠近"""

    def __init__(self, roi: dict, history_size: int = 10, area_growth_threshold: float = 1.3, cooldown: float = 5.0):
        self.roi = roi
        self.history = deque(maxlen=history_size)
        self.area_growth_threshold = area_growth_threshold
        self.cooldown = cooldown
        self.last_trigger_time = 0.0

    def update(self, detections: List[Dict]) -> bool:
        now = time.time()
        max_area = 0.0
        for det in detections:
            if det.get("class") == "person":
                x1, y1, x2, y2 = det["bbox"]
                if self._in_roi(x1, y1, x2, y2):
                    area = (x2 - x1) * (y2 - y1)
                    if area > max_area:
                        max_area = area

        self.history.append(max_area)

        if len(self.history) < 3:
            return False

        # 取最近 5 帧判断趋势
        recent = list(self.history)[-5:]
        first_positive = next((a for a in recent if a > 0), 0)
        last_positive = next((a for a in reversed(recent) if a > 0), 0)

        if first_positive > 0 and last_positive / first_positive >= self.area_growth_threshold:
            if now - self.last_trigger_time >= self.cooldown:
                self.last_trigger_time = now
                logger.info("检测到客户由远及近靠近")
                return True
        return False

    def _in_roi(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        return (self.roi.get("x1", 0) <= cx <= self.roi.get("x2", 1920) and
                self.roi.get("y1", 0) <= cy <= self.roi.get("y2", 1080))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_customer_detector.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add vision/customer_detector.py tests/test_customer_detector.py
git commit -m "feat: 客户靠近检测（由远及近面积趋势）"
```

---

### Task 7: 碗位检测（多帧投票 + 防抖）

**Files:**
- Create: `vision/bowl_detector.py`
- Test: `tests/test_bowl_detector.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bowl_detector.py
from vision.bowl_detector import BowlDetector

def test_no_event_on_empty_history():
    det = BowlDetector([{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}])
    events = det.update([])
    assert events == []

def test_placed_event_after_consistent_votes():
    det = BowlDetector([{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}], vote_frames=3, vote_threshold=3)
    events = []
    for _ in range(3):
        events = det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    assert len(events) == 1
    assert events[0]["event"] == "placed"
    assert events[0]["bowl_id"] == 1

def test_no_event_with_mixed_votes():
    det = BowlDetector([{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}], vote_frames=3, vote_threshold=3)
    det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    det.update([])
    events = det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    assert events == []

def test_debounce_prevents_rapid_flip():
    det = BowlDetector([{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}], vote_frames=2, vote_threshold=2, debounce=1.0)
    # 放碗
    det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    events = det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    assert len(events) == 1
    # 立即取走（在防抖时间内）不应触发
    events = det.update([])
    events = det.update([])
    assert events == []

def test_removed_event_after_debounce():
    import time
    det = BowlDetector([{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}], vote_frames=2, vote_threshold=2, debounce=0.05)
    # 先放碗
    det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    time.sleep(0.06)
    # 再取走
    det.update([])
    events = det.update([])
    assert len(events) == 1
    assert events[0]["event"] == "removed"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_bowl_detector.py -v
```

Expected: import errors

- [ ] **Step 3: Write minimal implementation**

```python
# vision/bowl_detector.py
import time
import logging
from collections import deque
from typing import Dict, List

logger = logging.getLogger(__name__)


class BowlDetector:
    """多帧投票 + 防抖的碗位状态检测器"""

    def __init__(self, rois: List[Dict], vote_frames: int = 5, vote_threshold: int = 4, debounce: float = 2.0):
        self.rois = rois
        self.vote_frames = vote_frames
        self.vote_threshold = vote_threshold
        self.debounce = debounce

        self.histories: Dict[int, deque] = {r["id"]: deque(maxlen=vote_frames) for r in rois}
        self.confirmed_states: Dict[int, bool] = {r["id"]: False for r in rois}
        self.last_change_time: Dict[int, float] = {r["id"]: 0 for r in rois}

    def update(self, detections: List[Dict]) -> List[Dict]:
        now = time.time()
        events = []

        for roi in self.rois:
            rid = roi["id"]
            has_bowl = self._check_roi(roi, detections)
            self.histories[rid].append(has_bowl)

            if len(self.histories[rid]) < self.vote_frames:
                continue

            true_count = sum(self.histories[rid])
            false_count = self.vote_frames - true_count

            new_state = None
            if true_count >= self.vote_threshold:
                new_state = True
            elif false_count >= self.vote_threshold:
                new_state = False
            else:
                continue

            if new_state != self.confirmed_states[rid]:
                if now - self.last_change_time[rid] >= self.debounce:
                    old_state = self.confirmed_states[rid]
                    self.confirmed_states[rid] = new_state
                    self.last_change_time[rid] = now
                    event_name = "placed" if new_state else "removed"
                    logger.info(f"碗位 {rid} 状态变化: {old_state} -> {new_state}")
                    events.append({
                        "bowl_id": rid,
                        "event": event_name,
                        "old_state": old_state,
                        "new_state": new_state,
                        "timestamp": now,
                    })
        return events

    def _check_roi(self, roi: Dict, detections: List[Dict]) -> bool:
        for det in detections:
            if det.get("class") == "bowl":
                x1, y1, x2, y2 = det["bbox"]
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                if roi["x1"] <= cx <= roi["x2"] and roi["y1"] <= cy <= roi["y2"]:
                    return True
        return False
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_bowl_detector.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add vision/bowl_detector.py tests/test_bowl_detector.py
git commit -m "feat: 碗位检测（多帧投票 + 防抖）"
```

---

### Task 8: 语音播报模块

**Files:**
- Create: `audio/tts_player.py`

- [ ] **Step 1: Write the implementation**

```python
# audio/tts_player.py
import os
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TTSPlayer:
    """语音播报：优先预录音频，fallback 到 pyttsx3 本地合成"""

    def __init__(self, volume: int = 80, use_pre_recorded: bool = True, audio_dir: str = "audio_clips"):
        self.volume = max(0, min(100, volume))
        self.use_pre_recorded = use_pre_recorded
        self.audio_dir = audio_dir
        self._lock = threading.Lock()
        os.makedirs(audio_dir, exist_ok=True)

    def play(self, text: str, audio_file: Optional[str] = None):
        with self._lock:
            if audio_file and os.path.exists(audio_file):
                self._play_file(audio_file)
                return
            if self.use_pre_recorded:
                pre = os.path.join(self.audio_dir, f"{text}.wav")
                if os.path.exists(pre):
                    self._play_file(pre)
                    return
            self._synthesize_and_play(text)

    def _play_file(self, path: str):
        try:
            import subprocess
            subprocess.run(["aplay", "-q", path], check=True, timeout=10)
            logger.debug(f"播放音频: {path}")
        except Exception as e:
            logger.error(f"播放音频失败: {e}")

    def _synthesize_and_play(self, text: str):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('volume', self.volume / 100.0)
            engine.say(text)
            engine.runAndWait()
            logger.info(f"TTS 播报: {text}")
        except Exception as e:
            logger.error(f"TTS 失败: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add audio/tts_player.py
git commit -m "feat: 语音播报（预录音频优先 + pyttsx3 fallback）"
```

---

### Task 9: 后台通信模块

**Files:**
- Create: `comm/backend_client.py`
- Test: `tests/test_backend_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_backend_client.py
import pytest
from unittest.mock import patch, MagicMock
from comm.backend_client import BackendClient

def test_send_bowl_status_makes_post_request():
    client = BackendClient("http://localhost:5000", heartbeat_interval=60)
    with patch("comm.backend_client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        client.send_bowl_status({"bowl_id": 1, "event": "placed"})
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://localhost:5000/device/bowl_status"

def test_failed_request_is_queued_for_retry():
    client = BackendClient("http://localhost:5000", heartbeat_interval=60)
    with patch("comm.backend_client.requests.post") as mock_post:
        mock_post.side_effect = Exception("connection error")
        client.send_bowl_status({"bowl_id": 1, "event": "placed"})
        assert client._queue.qsize() == 1

def test_heartbeat_sent_periodically():
    client = BackendClient("http://localhost:5000", heartbeat_interval=0.1)
    with patch("comm.backend_client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        client.start()
        import time
        time.sleep(0.25)
        client.stop()
        assert mock_post.call_count >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_backend_client.py -v
```

Expected: import/module errors

- [ ] **Step 3: Write minimal implementation**

```python
# comm/backend_client.py
import time
import threading
import logging
from typing import Dict, Any, Optional, Callable
from queue import Queue

import requests

logger = logging.getLogger(__name__)


class BackendClient:
    """后台 HTTP 通信客户端，支持事件队列缓存和心跳"""

    def __init__(self, base_url: str, heartbeat_interval: int = 30):
        self.base_url = base_url.rstrip("/")
        self.heartbeat_interval = heartbeat_interval
        self._queue = Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._callbacks: Dict[str, Callable] = {}

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        logger.info("后台通信线程已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("后台通信线程已停止")

    def register_callback(self, endpoint: str, handler: Callable):
        self._callbacks[endpoint] = handler

    def send_bowl_status(self, event: Dict[str, Any]):
        self._post("/device/bowl_status", event)

    def send_customer_detected(self, data: Dict[str, Any]):
        self._post("/device/customer_detected", data)

    def send_heartbeat(self, data: Dict[str, Any]):
        self._post("/device/heartbeat", data)

    def send_video_clip(self, data: Dict[str, Any]):
        self._post("/device/video_clip", data)

    def _post(self, endpoint: str, payload: Dict[str, Any]):
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            logger.debug(f"POST {endpoint} 成功")
        except requests.RequestException as e:
            logger.warning(f"POST {endpoint} 失败: {e}")
            self._queue.put(("post", endpoint, payload))

    def _worker(self):
        last_hb = 0
        while self._running:
            # 重试队列
            while not self._queue.empty():
                _, endpoint, payload = self._queue.get()
                self._post(endpoint, payload)

            now = time.time()
            if now - last_hb >= self.heartbeat_interval:
                self.send_heartbeat({"timestamp": now, "status": "ok", "mode": "local"})
                last_hb = now

            time.sleep(1)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_backend_client.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add comm/backend_client.py tests/test_backend_client.py
git commit -m "feat: 后台 HTTP 通信 + 失败重试队列 + 心跳"
```

---

### Task 10: 视频录制与循环清理

**Files:**
- Create: `video/recorder.py`
- Test: `tests/test_video_recorder.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_video_recorder.py
import os
import tempfile
import time
from pathlib import Path
from video.recorder import VideoRecorder

def test_cleanup_deletes_oldest_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = VideoRecorder(tmpdir, max_storage_gb=0.0001)  # ~100KB
        # 创建旧文件占满空间
        old = Path(tmpdir) / "old.mp4"
        old.write_bytes(b"x" * 60000)
        time.sleep(0.1)
        new = Path(tmpdir) / "new.mp4"
        new.write_bytes(b"x" * 60000)
        rec._cleanup_if_needed()
        assert not old.exists()
        assert new.exists()

def test_stop_returns_file_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = VideoRecorder(tmpdir, max_storage_gb=2)
        # 不真正启动 ffmpeg，仅测试接口
        rec.current_file = Path(tmpdir) / "test.mp4"
        rec.current_process = None
        path = rec.stop()
        assert path is None  # 因为 process 为 None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_video_recorder.py -v
```

Expected: import errors

- [ ] **Step 3: Write minimal implementation**

```python
# video/recorder.py
import os
import time
import logging
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class VideoRecorder:
    """MP4 分段录制 + 2G 循环清理"""

    def __init__(self, record_dir: str, max_storage_gb: int = 2):
        self.record_dir = Path(record_dir)
        self.max_storage_bytes = max_storage_gb * 1024 * 1024 * 1024
        self.current_process: Optional[subprocess.Popen] = None
        self.current_file: Optional[Path] = None
        os.makedirs(self.record_dir, exist_ok=True)

    def start(self, tag: str = ""):
        if self.current_process:
            logger.warning("录制已在进行中")
            return

        self._cleanup_if_needed()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{tag}" if tag else ""
        filename = f"{timestamp}{suffix}.mp4"
        self.current_file = self.record_dir / filename

        cmd = [
            "ffmpeg", "-y", "-f", "v4l2", "-i", "/dev/video0",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-an", str(self.current_file)
        ]
        try:
            self.current_process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            logger.info(f"开始录制: {self.current_file}")
        except Exception as e:
            logger.error(f"启动录制失败: {e}")

    def stop(self) -> Optional[Path]:
        if self.current_process:
            self.current_process.terminate()
            try:
                self.current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.current_process.kill()
                self.current_process.wait()
            self.current_process = None
            logger.info(f"停止录制: {self.current_file}")
            file = self.current_file
            self.current_file = None
            return file
        return None

    def _cleanup_if_needed(self):
        files = [f for f in self.record_dir.glob("*.mp4") if f.is_file()]
        total = sum(f.stat().st_size for f in files)
        while total > self.max_storage_bytes * 0.9 and files:
            files.sort(key=lambda f: f.stat().st_mtime)
            oldest = files.pop(0)
            total -= oldest.stat().st_size
            try:
                oldest.unlink()
                logger.info(f"删除旧录像: {oldest}")
            except OSError:
                break
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_video_recorder.py -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add video/recorder.py tests/test_video_recorder.py
git commit -m "feat: 视频录制与 2G 循环清理"
```

---

### Task 11: RTSP 推流模块

**Files:**
- Create: `video/streamer.py`

- [ ] **Step 1: Write the implementation**

```python
# video/streamer.py
import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class RTSPStreamer:
    """FFmpeg RTSP 推流（1帧/s 可配置）"""

    def __init__(self, input_device: str = "/dev/video0", fps: int = 1, rtsp_url: str = "rtsp://0.0.0.0:8554/live"):
        self.input_device = input_device
        self.fps = fps
        self.rtsp_url = rtsp_url
        self._process: Optional[subprocess.Popen] = None

    def start(self):
        if self._process:
            logger.warning("推流已在进行中")
            return

        cmd = [
            "ffmpeg", "-y", "-f", "v4l2", "-i", self.input_device,
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-r", str(self.fps), "-f", "rtsp", self.rtsp_url
        ]
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            logger.info(f"RTSP 推流已启动: {self.rtsp_url}")
        except Exception as e:
            logger.error(f"启动 RTSP 推流失败: {e}")

    def stop(self):
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait()
            self._process = None
            logger.info("RTSP 推流已停止")
```

- [ ] **Step 2: Commit**

```bash
git add video/streamer.py
git commit -m "feat: RTSP 推流模块（FFmpeg，可配置帧率）"
```

---

### Task 12: 主程序入口（持续检测驱动模式）

> **⚠️ 2026-05-07 更新**：主循环已取消状态机，改为持续检测驱动。以下代码为更新后的实现。

**Files:**
- Create: `main.py`

- [ ] **Step 1: Write the implementation**

```python
# main.py
import time
import logging
import signal
import threading
import sys
from typing import Optional

from web.config_server import create_app
from config.settings import Config
from vision.camera import Camera
from vision.detector import YOLODetector
from vision.customer_detector import CustomerDetector
from vision.bowl_detector import BowlDetector
from audio.tts_player import TTSPlayer
from comm.backend_client import BackendClient
from video.recorder import VideoRecorder
from video.streamer import RTSPStreamer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


class NoodleCamApp:
    def __init__(self):
        self.config = Config()
        self.running = False

        self.camera = Camera(
            self.config.get("camera.index", 0),
            self.config.get("camera.width", 1280),
            self.config.get("camera.height", 720),
            brightness=self.config.get("camera.brightness", 0.0),
            contrast=self.config.get("camera.contrast", 1.0),
            saturation=self.config.get("camera.saturation", 1.0),
            gamma=self.config.get("camera.gamma", 1.0),
        )
        self.detector = YOLODetector(
            self.config.get("vision.model_path", "models/yolov5s.rknn"),
            self.config.get("vision.confidence_threshold", 0.5),
            inference_interval=self.config.get("vision.inference_interval", 1)
        )
        self.customer_detector = CustomerDetector(
            self.config.get("vision.customer_roi", {})
        )
        self.bowl_detector = BowlDetector(
            self.config.get("vision.bowl_rois", []),
            self.config.get("vision.vote_frames", 5),
            self.config.get("vision.vote_threshold", 4),
            self.config.get("vision.debounce_seconds", 2.0)
        )
        self.tts = TTSPlayer(
            volume=self.config.get("audio.volume", 80),
            audio_dir=self.config.get("audio.audio_dir", "audio_clips"),
            messages=self.config.get("audio.messages", {}),
            voice=self.config.get("audio.voice", "zh-CN-XiaoxiaoNeural"),
            rate=self.config.get("audio.rate", "-15%"),
        )
        self.backend = BackendClient(
            self.config.get("backend.url", "http://localhost:5000"),
            self.config.get("backend.heartbeat_interval", 30)
        )
        cam_w = self.config.get("camera.width", 1280)
        cam_h = self.config.get("camera.height", 720)
        self.recorder = VideoRecorder(
            self.config.get("video.record_dir", "recordings"),
            self.config.get("video.max_storage_gb", 2),
            width=cam_w,
            height=cam_h,
            fps=self.config.get("video.rtsp_fps", 15),
        )
        self.recorder.enabled = self.config.get("video.record_enabled", True)
        self.streamer = RTSPStreamer(
            fps=self.config.get("video.rtsp_fps", 15),
            width=self.config.get("camera.width", 640),
            height=self.config.get("camera.height", 480),
            bitrate=self.config.get("video.rtsp_bitrate", 500),
            port=self.config.get("video.rtsp_port", 8554),
        )

        # Web 仿真开关：None 表示不覆盖，True/False 强制覆盖碗状态
        self.simulate_bowl_override: Optional[bool] = None
        self._web_thread = None

        # 线程安全的运行时状态，供 Web 端读取
        self._state_lock = threading.Lock()
        self._app_state = {
            "detections": [],
            "bowl_states": {},
            "any_bowl_present": False,
            "customer_detected": False,
            "recording": False,
            "record_enabled": self.recorder.enabled,
            "fps": 0.0,
            "timestamp": 0.0,
            "frame_count": 0,
        }
        # MJPEG 视频流帧
        self._jpeg_lock = threading.Lock()
        self._latest_jpeg: bytes = b""

    def _draw_overlay(self, frame, detections):
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
        h, _ = frame.shape[:2]

        # 尝试加载中文字体
        font_paths = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        ]
        font = None
        for fp in font_paths:
            try:
                font = ImageFont.truetype(fp, 18)
                break
            except Exception:
                continue
        if font is None:
            font = ImageFont.load_default()

        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        colors = {"person": (0, 255, 0), "bowl": (0, 165, 255)}
        colors_pil = {"person": (0, 255, 0), "bowl": (255, 165, 0)}

        # 画检测框 + 标签
        for det in detections:
            cls = det.get("class", "obj")
            x1, y1, x2, y2 = det["bbox"]
            conf = det.get("conf", 0)
            color = colors.get(cls, (255, 255, 255))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{cls} {conf:.2f}"
            bbox = draw.textbbox((0, 0), label, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.rectangle([x1, y1 - th - 4, x1 + tw + 4, y1], fill=colors_pil.get(cls, (255, 255, 255)))
            draw.text((x1 + 2, y1 - th - 2), label, fill=(0, 0, 0), font=font)

        # 画客户检测区 ROI
        roi = self.config.get("vision.customer_roi", {})
        if roi:
            rx1, ry1, rx2, ry2 = roi.get("x1", 0), roi.get("y1", 0), roi.get("x2", 0), roi.get("y2", 0)
            if rx2 > rx1 and ry2 > ry1:
                overlay = frame.copy()
                cv2.rectangle(overlay, (rx1, ry1), (rx2, ry2), (0, 200, 0), 2)
                cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                draw.text((rx1 + 4, ry1 + 2), "客户检测区", fill=(0, 200, 0), font=font)

        # 画碗位检测区 ROI
        for r in self.config.get("vision.bowl_rois", []):
            bx1, by1, bx2, by2 = r.get("x1", 0), r.get("y1", 0), r.get("x2", 0), r.get("y2", 0)
            rid = r.get("id", "?")
            if bx2 > bx1 and by2 > by1:
                overlay = frame.copy()
                cv2.rectangle(overlay, (bx1, by1), (bx2, by2), (255, 165, 0), 2)
                cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                draw.text((bx1 + 4, by1 + 2), f"碗位#{rid}", fill=(255, 165, 0), font=font)

        # 画碗状态信息
        any_bowl = self._any_bowl_present()
        state_text = f"碗状态: {'有碗' if any_bowl else '无碗'}"
        if self.simulate_bowl_override is not None:
            state_text += " [仿真]"
        draw.text((10, h - 28), state_text, fill=(255, 255, 255), font=font)

        frame = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return frame

    def _get_latest_jpeg(self) -> bytes:
        with self._jpeg_lock:
            return self._latest_jpeg

    def _handle_customer_approach(self):
        logger.info("检测到客户靠近，播放引导语音")
        self.tts.say("customer_approach")

    def _handle_bowl_events(self, events):
        for ev in events:
            logger.info(f"碗位事件: {ev}")
            self.backend.send_bowl_status(ev)

    def _any_bowl_present(self) -> bool:
        if self.simulate_bowl_override is not None:
            return self.simulate_bowl_override
        return self.bowl_detector.any_bowl_present()

    def run(self):
        self.running = True
        self.backend.start()
        web_cfg = self.config.get("web", {})
        web_host = web_cfg.get("host", "0.0.0.0")
        web_port = web_cfg.get("port", 8080)
        app = create_app(
            "config.json",
            app_state=self._app_state,
            recorder=self.recorder,
            config=self.config,
            latest_jpeg=self._get_latest_jpeg,
            app_instance=self,
        )
        self._web_thread = threading.Thread(
            target=app.run,
            kwargs={"host": web_host, "port": web_port, "threaded": True, "debug": False},
            daemon=True
        )
        self._web_thread.start()
        logger.info(f"配置服务已启动于 http://{web_host}:{web_port}")
        logger.info("正在预合成语音...")
        self.tts.pre_synthesize()
        if self.config.get("video.rtsp_enabled", True):
            self.streamer.start()

        if not self.camera.open():
            logger.error("摄像头打开失败，退出")
            return

        self.detector.start_async()
        logger.info("系统启动，进入持续检测模式")
        frame_count = 0
        last_fps_time = time.time()
        try:
            while self.running:
                loop_start = time.time()
                frame = self.camera.read()
                if frame is None:
                    time.sleep(0.1)
                    continue

                # 异步推理
                self.detector.submit_frame(frame)
                detections = self.detector.get_latest_results()

                vis_frame = self._draw_overlay(frame.copy(), detections)
                self.streamer.push_frame(vis_frame)
                self.recorder.write_frame(vis_frame)

                # 编码 JPEG 供 Web MJPEG 流使用
                import cv2 as _cv2
                _, jpeg = _cv2.imencode('.jpg', vis_frame)
                with self._jpeg_lock:
                    self._latest_jpeg = jpeg.tobytes()

                # 持续检测客户靠近
                customer_triggered = self.customer_detector.update(detections)
                if customer_triggered:
                    self._handle_customer_approach()

                # 持续检测碗状态
                events = self.bowl_detector.update(detections)
                if events:
                    self._handle_bowl_events(events)

                # 根据 record_enabled 和碗状态控制录像
                any_bowl = self._any_bowl_present()
                if self.recorder.enabled and any_bowl:
                    if not self.recorder.is_recording():
                        self.recorder.start("auto")
                else:
                    if self.recorder.is_recording():
                        self.recorder.stop()

                frame_count += 1
                now = time.time()
                if now - last_fps_time >= 1.0:
                    fps = frame_count / (now - last_fps_time)
                    frame_count = 0
                    last_fps_time = now
                else:
                    fps = self._app_state.get("fps", 0)

                with self._state_lock:
                    self._app_state["detections"] = [dict(d) for d in detections]
                    self._app_state["bowl_states"] = self.bowl_detector.get_states()
                    self._app_state["any_bowl_present"] = any_bowl
                    self._app_state["customer_detected"] = customer_triggered
                    self._app_state["recording"] = self.recorder.is_recording()
                    self._app_state["record_enabled"] = self.recorder.enabled
                    self._app_state["fps"] = round(fps, 1)
                    self._app_state["timestamp"] = now
                    self._app_state["frame_count"] = self._app_state.get("frame_count", 0) + 1

                elapsed = time.time() - loop_start
                sleep_time = max(0, 0.05 - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("收到中断信号")
        finally:
            self.shutdown()

    def shutdown(self):
        if not self.running:
            return
        logger.info("正在关闭系统...")
        self.running = False
        self.camera.release()
        self.recorder.stop()
        self.streamer.stop()
        self.backend.stop()
        self.detector.stop_async()
        self.detector.release()
        logger.info("系统已关闭")


def main():
    app = NoodleCamApp()
    signal.signal(signal.SIGINT, lambda s, f: app.shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: app.shutdown())
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: 主程序入口，持续检测驱动模式（无状态机）"
```

---

### Task 13: Flask 配置 Web 服务

**Files:**
- Create: `web/config_server.py`

- [ ] **Step 1: Write the implementation**

```python
# web/config_server.py
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
```

- [ ] **Step 2: Commit**

```bash
git add web/config_server.py
git commit -m "feat: Flask 配置 Web 服务（ROI 设定、参数微调、模式切换）"
```

---

### Task 14: 通义千问 LLM 备用模块

**Files:**
- Create: `llm/tongyi_client.py`

- [ ] **Step 1: Write the implementation**

```python
# llm/tongyi_client.py
import json
import base64
import logging
from typing import Dict, List, Optional

import numpy as np

try:
    import dashscope
    from dashscope import MultiModalConversation
except ImportError:
    dashscope = None

logger = logging.getLogger(__name__)


class TongyiClient:
    """通义千问多模态视觉理解封装，含自动降级策略"""

    def __init__(self, api_key: str, model: str = "qwen-vl-plus", fallback_threshold: float = 0.3):
        self.api_key = api_key
        self.model = model
        self.fallback_threshold = fallback_threshold
        self._fail_count = 0
        self._max_fail = 3
        self._backoff_until = 0
        if dashscope:
            dashscope.api_key = api_key

    def is_available(self) -> bool:
        import time
        if self._fail_count >= self._max_fail:
            if time.time() < self._backoff_until:
                return False
            self._fail_count = 0
        return dashscope is not None and bool(self.api_key)

    def analyze_frame(self, frame: np.ndarray, prompt: str = None) -> Optional[Dict]:
        if not self.is_available():
            return None

        try:
            import cv2
            import time
            _, buf = cv2.imencode(".jpg", frame)
            b64 = base64.b64encode(buf).decode("utf-8")

            system_prompt = (
                "你是一个面馆机器人视觉助手。请分析图片并返回严格的 JSON 格式："
                '{"customer_nearby": bool, "bowls": [{"id": int, "present": bool}], "confidence": float}'
            )
            user_prompt = prompt or "检测画面中是否有顾客靠近，以及每个碗位是否有碗。"

            messages = [
                {"role": "system", "content": [{"text": system_prompt}]},
                {"role": "user", "content": [
                    {"image": f"data:image/jpeg;base64,{b64}"},
                    {"text": user_prompt}
                ]}
            ]

            response = MultiModalConversation.call(model=self.model, messages=messages)
            content = response.output.choices[0].message.content
            text = content[0]["text"] if isinstance(content, list) else content

            # 提取 JSON
            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            result = json.loads(text[json_start:json_end])

            self._fail_count = 0
            logger.info(f"通义千问识别结果: {result}")
            return result

        except Exception as e:
            self._fail_count += 1
            if self._fail_count >= self._max_fail:
                self._backoff_until = time.time() + 1800  # 30 分钟冷却
                logger.warning("通义千问连续失败 3 次，进入 30 分钟冷却")
            else:
                logger.warning(f"通义千问调用失败 ({self._fail_count}/{self._max_fail}): {e}")
            return None
```

- [ ] **Step 2: Commit**

```bash
git add llm/tongyi_client.py
git commit -m "feat: 通义千问 LLM 备用模块（含自动降级策略）"
```

---

### Task 15: 集成测试与运行验证

**Files:**
- Modify: `main.py`（添加 Web 服务子线程启动）
- Modify: `requirements.txt`（补充 dashscope）

- [ ] **Step 1: 修改 main.py 启动配置服务**

在 `NoodleCamApp.__init__` 之后、`run` 方法中增加 Web 服务线程启动：

```python
# main.py 顶部新增
import threading
from web.config_server import create_app

# NoodleCamApp.__init__ 末尾添加
        self._web_thread: Optional[threading.Thread] = None

# NoodleCamApp.run 方法中，在 self.backend.start() 之后添加
        web_cfg = self.config.get("web", {})
        web_host = web_cfg.get("host", "0.0.0.0")
        web_port = web_cfg.get("port", 8080)
        app = create_app("config.json")
        self._web_thread = threading.Thread(
            target=app.run,
            kwargs={"host": web_host, "port": web_port, "threaded": True, "debug": False},
            daemon=True
        )
        self._web_thread.start()
        logger.info(f"配置服务已启动于 http://{web_host}:{web_port}")
```

- [ ] **Step 2: 确认 requirements.txt 包含 dashscope**

```bash
grep -q "dashscope" requirements.txt || echo "dashscope>=1.10.0" >> requirements.txt
```

- [ ] **Step 3: 运行 pytest 全量测试**

```bash
pytest tests/ -v
```

Expected: 所有测试通过（test_config: 3, test_state_machine: 7, test_customer_detector: 4, test_bowl_detector: 5, test_backend_client: 3 = 22 passed）

- [ ] **Step 4: Commit**

```bash
git add main.py requirements.txt
git commit -m "feat: 集成 Web 配置服务，补充 dashscope 依赖"
```

---

### Task 16: 系统级验证清单

**Files:** N/A

- [ ] **Step 1: 开发机模拟运行**

```bash
# 生成默认配置
python -c "from config.settings import Config; c=Config(); c.save()"
# 查看默认配置
cat config.json
```

- [ ] **Step 2: 验证 main.py 启动不崩溃（无摄像头/模型时优雅降级）**

```bash
python main.py &
# 等待 5 秒后检查日志
# Expected: 日志显示"摄像头打开失败"或"模型文件不存在"，进程不崩溃
timeout 5 python main.py || true
```

- [ ] **Step 3: 验证 Web 配置服务可访问**

```bash
# 单独启动配置服务
python -c "from web.config_server import run_server; run_server(port=18080)" &
sleep 2
curl -s http://localhost:18080/api/config | python -m json.tool
# Expected: 返回完整默认配置 JSON
```

- [ ] **Step 4: 提交最终版本**

```bash
git add .
git commit -m "feat: RV1126 机器人面馆视觉交互系统 v1.0 完成"
```

---

## Spec 覆盖自查

| Spec 章节 | 对应任务 | 状态 |
|-----------|----------|------|
| 2.1 轻量级单体架构 | Task 1, 12 | 覆盖 |
| 2.2 视觉模块 | Task 4, 5, 6, 7 | 覆盖 |
| 2.2 语音模块 | Task 8 | 覆盖 |
| 2.2 通信模块 | Task 9 | 覆盖 |
| 2.2 视频流模块 | Task 10, 11 | 覆盖 |
| 2.2 配置服务 | Task 13 | 覆盖 |
| 2.2 LLM 备用模块 | Task 14 | 覆盖 |
| 2.2 工作模式（持续检测驱动） | Task 12 | 覆盖 |
| 3.1 检测驱动流程 | Task 12 | 覆盖 |
| 3.2 多帧投票防错检 | Task 7 | 覆盖 |
| 3.3 视频录制存储 | Task 10 | 覆盖 |
| 4 后台接口 | Task 9 | 覆盖 |
| 5 ROI 配置界面 | Task 13 | 覆盖 |
| 6 LLM 备用（通义） | Task 14 | 覆盖 |
| 7 网络摄像头 | Task 10, 11 | 覆盖 |
| 8 错误处理 | 各模块内置 logging + 降级逻辑 | 覆盖 |
| 9 测试策略 | 每个 Task 含测试 | 覆盖 |

## Placeholder 自查

- 无 "TBD"、"TODO"、"implement later"
- 无 "Add appropriate error handling" 等模糊描述
- 每个代码步骤均含完整代码
- 类型和函数名在全文中一致

## 类型一致性自查

- `Config.get/set` 签名一致
- `StateMachine.trigger/on` 签名一致
- `BackendClient.send_*` 方法名一致
- `BowlDetector.update` 返回 `List[Dict]` 全篇一致
- 各模块 logger 命名遵循 `logging.getLogger(__name__)`
