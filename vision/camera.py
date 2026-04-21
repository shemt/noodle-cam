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
