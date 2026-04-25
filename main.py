import time
import logging
import signal
import threading
import sys

from web.config_server import create_app
from pathlib import Path

from config.settings import Config
from core.state_machine import StateMachine, State
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
            self.config.get("camera.height", 720)
        )
        self.detector = YOLODetector(
            self.config.get("vision.model_path", "models/yolov5s.rknn"),
            self.config.get("vision.confidence_threshold", 0.5)
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
        )
        cam_index = self.config.get("camera.index", 0)
        video_device = f"/dev/video{cam_index}"
        self.backend = BackendClient(
            self.config.get("backend.url", "http://localhost:5000"),
            self.config.get("backend.heartbeat_interval", 30)
        )
        self.recorder = VideoRecorder(
            self.config.get("video.record_dir", "recordings"),
            self.config.get("video.max_storage_gb", 2),
            input_device=video_device
        )
        self.streamer = RTSPStreamer(
            fps=self.config.get("video.rtsp_fps", 15),
            width=self.config.get("camera.width", 640),
            height=self.config.get("camera.height", 480),
            bitrate=self.config.get("video.rtsp_bitrate", 500),
            port=self.config.get("video.rtsp_port", 8554),
        )
        self.sm = StateMachine()
        self._setup_state_handlers()
        self._web_thread = None

    def _setup_state_handlers(self):
        self.sm.on("customer_approach", self._on_customer_approach)
        self.sm.on("bowl_placed", self._on_bowl_placed)
        self.sm.on("meal_ready", self._on_meal_ready)
        self.sm.on("bowl_removed", self._on_bowl_removed)

    def _draw_overlay(self, frame, detections):
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
        h, w = frame.shape[:2]

        # 尝试加载中文字体
        font_paths = [
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

        # 用 PIL 绘制文字，先转为 RGB
        pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        draw = ImageDraw.Draw(pil_img)

        colors = {"person": (0, 255, 0), "bowl": (0, 165, 255)}
        colors_pil = {"person": (0, 255, 0), "bowl": (255, 165, 0)}

        # 画检测框 (OpenCV) + 标签 (PIL)
        for det in detections:
            cls = det.get("class", "obj")
            x1, y1, x2, y2 = det["bbox"]
            conf = det.get("conf", 0)
            color = colors.get(cls, (255, 255, 255))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            label = f"{cls} {conf:.2f}"
            # PIL 文字背景
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

        # 画状态信息
        state_text = f"状态: {self.sm.state.name}"
        draw.text((10, h - 28), state_text, fill=(255, 255, 255), font=font)

        # PIL RGB 转回 OpenCV BGR
        frame = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return frame

    def _on_customer_approach(self, old, new, ctx):
        logger.info("检测到客户靠近，播放引导语音")
        self.tts.say("customer_approach")
        self.recorder.start("order")

    def _on_bowl_placed(self, old, new, ctx):
        event = ctx.get("event")
        logger.info(f"检测到放碗: {event}")
        self.backend.send_bowl_status(event)
        self.tts.say("bowl_placed")

    def _on_meal_ready(self, old, new, ctx):
        logger.info("餐品制作完成，通知取餐")
        self.tts.say("meal_ready")
        self.recorder.stop()

    def _on_bowl_removed(self, old, new, ctx):
        event = ctx.get("event")
        logger.info(f"碗被取走: {event}")
        self.backend.send_bowl_status(event)
        self.tts.say("bowl_removed")
        self.recorder.stop()

    def run(self):
        self.running = True
        self.backend.start()
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
        logger.info("正在预合成语音...")
        self.tts.pre_synthesize()
        if self.config.get("video.rtsp_enabled", True):
            self.streamer.start()

        if not self.camera.open():
            logger.error("摄像头打开失败，退出")
            return

        logger.info("系统启动，进入空闲状态")
        try:
            while self.running:
                frame = self.camera.read()
                if frame is None:
                    time.sleep(0.1)
                    continue

                detections = self.detector.detect(frame)
                vis_frame = self._draw_overlay(frame.copy(), detections)
                self.streamer.push_frame(vis_frame)

                if self.sm.state == State.IDLE:
                    if self.customer_detector.update(detections):
                        self.sm.trigger("customer_approach")

                elif self.sm.state in (State.GUIDING, State.COOKING):
                    events = self.bowl_detector.update(detections)
                    for ev in events:
                        if ev["event"] == "placed":
                            self.sm.trigger("bowl_placed", event=ev)
                        elif ev["event"] == "removed":
                            self.sm.trigger("bowl_removed", event=ev)

                elif self.sm.state == State.WAITING:
                    events = self.bowl_detector.update(detections)
                    for ev in events:
                        if ev["event"] == "removed":
                            self.sm.trigger("bowl_removed", event=ev)

                time.sleep(0.05)
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
        self.detector.release()
        logger.info("系统已关闭")


def main():
    app = NoodleCamApp()
    signal.signal(signal.SIGINT, lambda s, f: app.shutdown())
    signal.signal(signal.SIGTERM, lambda s, f: app.shutdown())
    app.backend.register_callback("/device/notify_meal_ready", lambda data: app.sm.trigger("meal_ready"))
    app.run()


if __name__ == "__main__":
    main()
