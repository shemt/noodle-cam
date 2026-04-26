# NoodleCam 机器人面馆视觉交互系统

基于 RV1126/RK3588 NPU + YOLOv5 目标检测 + Flask Web 配置 + MJPEG 实时监控 + TTS 语音引导 + GStreamer RTSP 推流。

## 系统架构

```
摄像头 (v4l2) → OpenCV 读取帧 → YOLO 检测 (RKNN/OpenCV DNN)
                                    ↓
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
            Flask MJPEG 流     状态机驱动交互     RTSP GStreamer
                    ↓               ↓               ↓
            Web 监控页面      TTS 语音播报      局域网拉流
                    ↓               ↓
            ROI 框选配置      后端 HTTP 通信
```

## 核心模块

| 模块 | 路径 | 说明 |
|------|------|------|
| 主程序 | `main.py` | 初始化所有模块，主循环读取摄像头、检测、状态机、推流 |
| 检测器 | `vision/detector.py` | YOLOv5 RKNN NPU 推理，fallback 到 OpenCV DNN (ONNX) |
| 摄像头 | `vision/camera.py` | OpenCV VideoCapture 封装，支持自动重连 |
| 客户检测 | `vision/customer_detector.py` | 人形框面积增长趋势判断客户靠近 |
| 碗位检测 | `vision/bowl_detector.py` | 多帧投票 + 防抖的碗位状态检测 |
| 状态机 | `core/state_machine.py` | IDLE → GUIDING → COOKING → WAITING |
| TTS | `audio/tts_player.py` | edge-tts 合成 + afplay/aplay 播放 |
| 录像 | `video/recorder.py` | ffmpeg v4l2 录制 (Linux only)，支持开关控制 |
| RTSP | `video/streamer.py` | GStreamer appsrc RTSP 服务器 |
| Web | `web/config_server.py` | Flask 配置服务 + 监控页面 + 录像管理 + MJPEG 流 |
| 后端 | `comm/backend_client.py` | HTTP 事件上报 + 心跳 |
| 配置 | `config/settings.py` | JSON 配置读写 + 深合并默认值 |

## Web 功能

访问 `http://<设备IP>:8090`

### 配置页面 (`/`)

- YOLO 置信度阈值、多帧投票数、防抖时间
- 语音播报文字自定义
- LLM 备用模式切换

### 监控页面 (`/monitor`)

- **实时视频画面**：MJPEG 流 `/video_feed`，画面上已叠加检测框（绿色=人，橙色=碗）和 ROI 区域
- **ROI 区域设定**：在视频画面上方直接拖拽框选客户检测区和碗位检测区，所见即所得
- **系统概览**：状态机状态、FPS、录像状态、检测目标数量
- **检测目标表格**：实时显示人和碗的类别、置信度、边界框
- **录像开关**：一键开启/关闭录像，同步持久化到 `config.json`

### 录像管理页面 (`/recordings`)

- 录像文件列表（文件名、大小、修改时间）
- 下载、删除操作

## API 列表

| 接口 | 方法 | 说明 |
|------|------|------|
| `/video_feed` | GET | MJPEG 实时视频流（multipart/x-mixed-replace） |
| `/api/status` | GET | 实时状态 JSON（detections / state / fps / recording / record_enabled） |
| `/api/recording` | POST | 切换录像开关 `{enabled: bool}` |
| `/api/recordings` | GET | 录像文件列表 |
| `/api/recordings/<name>` | DELETE | 删除指定录像 |
| `/recordings/<name>` | GET | 下载录像文件 |
| `/api/config` | GET/POST | 读取/保存配置 |

## 状态机

```
IDLE ──customer_approach──→ GUIDING ──bowl_placed──→ COOKING
  ↑                                              │
  │                    meal_ready                │
  │                          ↓                   │
  └── bowl_removed ── WAITING ←──────────────────┘
```

| 状态 | 行为 |
|------|------|
| IDLE | 检测客户靠近 → 播放引导语音 + 开始录像 |
| GUIDING | 检测碗放置 → 上报状态 + 播放提示 |
| COOKING | 等待后端通知餐品就绪 → 停止录像 + 播放取餐提示 |
| WAITING | 检测碗取走 → 上报状态 + 播放慢用提示 + 停止录像 |

## 本机调试（macOS/Linux）

### 1. 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
brew install ffmpeg  # macOS，用于 TTS 音频转 wav
```

### 2. 下载 ONNX 模型（可选，无模型则检测返回空结果）

```bash
mkdir -p models
curl -L -o models/yolov5s.onnx \
  "https://github.com/ultralytics/yolov5/releases/download/v7.0/yolov5s.onnx"
```

修改 `config.json`：
```json
"vision": { "model_path": "models/yolov5s.onnx" }
```

### 3. 运行

```bash
python main.py
```

- 首次运行需授权摄像头权限
- 非 Linux 平台自动跳过 v4l2 录制
- GStreamer RTSP 未安装时会自动跳过
- Web 服务运行于 `http://0.0.0.0:8090`

### 4. 关闭 RTSP（可选）

```json
"video": { "rtsp_enabled": false }
```

## RV1126/RK3588 部署

### 1. 依赖

```bash
pip install opencv-python numpy Pillow requests Flask edge-tts dashscope
# 系统包
apt install ffmpeg gstreamer1.0-plugins-ugly aplay
```

### 2. RKNN 模型

将 `yolov5s_rk3588.rknn` 放到 `models/` 目录，修改 `config.json`：
```json
"vision": { "model_path": "models/yolov5s_rk3588.rknn" }
```

### 3. 字体

确保系统安装了中文字体：
```bash
apt install fonts-wqy-zenhei
```

### 4. 启动

```bash
nohup python main.py > app.log 2>&1 &
```

## 配置说明（config.json）

```json
{
  "camera": { "index": 0, "width": 1280, "height": 720 },
  "vision": {
    "model_path": "models/yolov5s_rk3588.rknn",
    "confidence_threshold": 0.5,
    "customer_roi": { "x1": 0, "y1": 0, "x2": 640, "y2": 480 },
    "bowl_rois": [],
    "vote_frames": 5,
    "vote_threshold": 4,
    "debounce_seconds": 2.0
  },
  "audio": {
    "volume": 80,
    "audio_dir": "audio_clips",
    "voice": "zh-CN-XiaoxiaoNeural",
    "messages": {
      "customer_approach": "请拿碗放在碗托上",
      "meal_ready": "您的餐已准备好，请取餐",
      "bowl_placed": "已检测到放碗",
      "bowl_removed": "碗已取走，请慢用"
    }
  },
  "backend": { "url": "http://localhost:5000", "heartbeat_interval": 86400 },
  "video": {
    "rtsp_enabled": true,
    "rtsp_fps": 15,
    "rtsp_port": 8554,
    "rtsp_bitrate": 500,
    "record_enabled": true,
    "record_dir": "recordings",
    "max_storage_gb": 2
  },
  "web": { "host": "0.0.0.0", "port": 8090 }
}
```

## 开发记录

### v1.0 功能清单

- [x] RKNN NPU 目标检测（人/碗）+ ONNX OpenCV DNN fallback
- [x] 状态机驱动交互流程（IDLE → GUIDING → COOKING → WAITING）
- [x] GStreamer appsrc RTSP 推流
- [x] MJPEG Web 实时视频流（带检测框和 ROI 叠加）
- [x] Web 监控页面：视频 + ROI 框选 + 系统状态 + 检测目标 + 录像开关
- [x] Web 配置页面：参数微调 + 语音播报文字
- [x] Web 录像管理页面：列表 + 下载 + 删除
- [x] edge-tts 语音合成，消息可配置
- [x] 视频录像（ffmpeg v4l2）+ 2GB 循环清理
- [x] 后端 HTTP 通信 + 心跳
- [x] 跨平台支持（Linux ARM / macOS x86）

### 关键修复

| 时间 | 问题 | 修复 |
|------|------|------|
| 2026-04-25 | RKNN batch 维度解析错误 | ONNX 输出 reshape + 坐标按 input_size 映射 |
| 2026-04-25 | RTSP v4l2 设备冲突 | 改用 appsrc 从主循环推送帧 |
| 2026-04-25 | 中文 OSD 乱码 | PIL/Pillow + 系统字体替代 cv2.putText |
| 2026-04-25 | macOS 本机调试 | afplay / aplay 自动切换，非 Linux 跳过 v4l2 |
| 2026-04-25 | MJPEG 切换页面后黑屏 | Connection: close + 异常捕获 + onerror 重试 |

## 项目结构

```
.
├── main.py                  # 主程序入口
├── config/
│   ├── settings.py          # Config 类
│   └── config.json          # 运行时配置（自动生成）
├── core/
│   └── state_machine.py     # 状态机
├── vision/
│   ├── camera.py            # 摄像头
│   ├── detector.py          # YOLO 检测器
│   ├── customer_detector.py # 客户靠近检测
│   └── bowl_detector.py     # 碗位状态检测
├── audio/
│   └── tts_player.py        # TTS 语音播报
├── video/
│   ├── recorder.py          # 视频录制
│   └── streamer.py          # RTSP 推流
├── web/
│   └── config_server.py     # Flask Web 服务
├── comm/
│   └── backend_client.py    # 后端通信
├── requirements.txt
└── README.md
```
