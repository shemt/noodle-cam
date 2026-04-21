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
            self.config.get("audio.volume", 80),
            self.config.get("audio.pre_recorded", True),
            self.config.get("audio.audio_dir", "audio_clips")
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
            input_device=video_device,
            fps=self.config.get("video.rtsp_fps", 1)
        )
        self.sm = StateMachine()
        self._setup_state_handlers()
        self._web_thread = None

    def _setup_state_handlers(self):
        self.sm.on("customer_approach", self._on_customer_approach)
        self.sm.on("bowl_placed", self._on_bowl_placed)
        self.sm.on("meal_ready", self._on_meal_ready)
        self.sm.on("bowl_removed", self._on_bowl_removed)

    def _on_customer_approach(self, old, new, ctx):
        logger.info("检测到客户靠近，播放引导语音")
        self.tts.play("请拿碗放在碗托上")
        self.recorder.start("order")

    def _on_bowl_placed(self, old, new, ctx):
        event = ctx.get("event")
        logger.info(f"检测到放碗: {event}")
        self.backend.send_bowl_status(event)

    def _on_meal_ready(self, old, new, ctx):
        logger.info("餐品制作完成，通知取餐")
        self.tts.play("您的餐已准备好，请取餐")
        self.recorder.stop()

    def _on_bowl_removed(self, old, new, ctx):
        event = ctx.get("event")
        logger.info(f"碗被取走: {event}")
        self.backend.send_bowl_status(event)
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
