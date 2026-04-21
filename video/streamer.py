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
