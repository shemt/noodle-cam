import os
import signal
import logging
import subprocess
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime

try:
    import cv2
except ImportError:
    cv2 = None

logger = logging.getLogger(__name__)


class VideoRecorder:
    """MP4 分段录制 + 2G 循环清理。
    通过 ffmpeg stdin 接收 OpenCV BGR 帧，不再直接访问 v4l2 设备，
    避免与主循环的 VideoCapture 冲突。
    """

    def __init__(self, record_dir: str, max_storage_gb: int = 2, width: int = 1280, height: int = 720, fps: int = 15):
        self.record_dir = Path(record_dir)
        self.max_storage_bytes = max_storage_gb * 1024 * 1024 * 1024
        self.width = width
        self.height = height
        self.fps = fps
        self.current_process: Optional[subprocess.Popen] = None
        self.current_file: Optional[Path] = None
        self.enabled = True
        os.makedirs(self.record_dir, exist_ok=True)

    def start(self, tag: str = ""):
        if not self.enabled:
            logger.debug("录制已禁用，跳过")
            return
        if self.current_process:
            logger.warning("录制已在进行中")
            return

        self._cleanup_if_needed()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = f"_{tag}" if tag else ""
        filename = f"noodlecam_{timestamp}{suffix}.mp4"
        self.current_file = self.record_dir / filename

        size = f"{self.width}x{self.height}"
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-pix_fmt", "bgr24",
            "-s", size, "-r", str(self.fps),
            "-i", "-",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
            "-movflags", "+faststart",
            "-an", str(self.current_file)
        ]
        try:
            self.current_process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
            logger.info(f"开始录制: {self.current_file}")
        except Exception as e:
            logger.error(f"启动录制失败: {e}")

    def write_frame(self, frame) -> bool:
        """将一帧 OpenCV BGR 图像写入 ffmpeg stdin。"""
        if self.current_process is None or self.current_process.poll() is not None:
            return False
        try:
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                import cv2
                frame = cv2.resize(frame, (self.width, self.height))
            self.current_process.stdin.write(frame.tobytes())
            return True
        except (BrokenPipeError, OSError) as e:
            logger.warning(f"写入录制帧失败: {e}")
            return False

    def stop(self) -> Optional[Path]:
        if self.current_process:
            # 先关闭 stdin 停止输入，再发送 SIGINT 让 ffmpeg 优雅完成编码
            try:
                self.current_process.stdin.close()
            except Exception:
                pass
            try:
                self.current_process.send_signal(signal.SIGINT)
                self.current_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("ffmpeg 优雅退出超时，强制终止")
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

    def is_recording(self) -> bool:
        return self.current_process is not None and self.current_process.poll() is None

    def list_recordings(self) -> List[Dict]:
        files = []
        for f in sorted(self.record_dir.glob("noodlecam_*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
            if f.is_file():
                st = f.stat()
                files.append({
                    "name": f.name,
                    "size": st.st_size,
                    "mtime": st.st_mtime,
                })
        return files

    def delete_recording(self, name: str) -> bool:
        target = self.record_dir / name
        try:
            # 安全检查：确保文件在 recordings 目录内
            target.resolve().relative_to(self.record_dir.resolve())
        except ValueError:
            logger.warning(f"非法路径: {name}")
            return False
        if target.exists() and target.is_file():
            try:
                target.unlink()
                logger.info(f"删除录像: {target}")
                return True
            except OSError as e:
                logger.error(f"删除录像失败: {e}")
        return False

    def _cleanup_if_needed(self):
        files = [f for f in self.record_dir.glob("noodlecam_*.mp4") if f.is_file()]
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
