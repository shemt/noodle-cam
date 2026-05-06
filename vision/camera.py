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
    """摄像头封装，支持自动重连与图像增强（亮度/对比度/饱和度/伽马）"""

    def __init__(
        self,
        index: int = 0,
        width: int = 1280,
        height: int = 720,
        brightness: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        gamma: float = 1.0,
    ):
        self.index = index
        self.width = width
        self.height = height
        self.brightness = brightness
        self.contrast = contrast
        self.saturation = saturation
        self.gamma = gamma
        self._cap = None
        self._reconnect_attempts = 0
        self._max_reconnect = 3
        self._gamma_lut: Optional[np.ndarray] = None
        self._update_gamma_lut()

    def _update_gamma_lut(self):
        if cv2 is None or self.gamma == 1.0:
            self._gamma_lut = None
            return
        inv_gamma = 1.0 / self.gamma
        self._gamma_lut = np.array(
            [((i / 255.0) ** inv_gamma) * 255 for i in range(256)]
        ).astype(np.uint8)

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

        # 图像增强处理
        frame = self._enhance(frame)
        return frame

    def _enhance(self, frame: np.ndarray) -> np.ndarray:
        """应用亮度/对比度/饱和度/伽马校正"""
        # 1. 亮度 + 对比度
        if self.contrast != 1.0 or self.brightness != 0.0:
            frame = cv2.convertScaleAbs(frame, alpha=self.contrast, beta=self.brightness)

        # 2. 伽马校正
        if self._gamma_lut is not None:
            frame = cv2.LUT(frame, self._gamma_lut)

        # 3. 饱和度
        if self.saturation != 1.0:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[:, :, 1] *= self.saturation
            hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)
            frame = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)

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
