import time
import logging
import subprocess
import glob
from typing import Optional
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

logger = logging.getLogger(__name__)


class Camera:
    """摄像头封装，支持自动重连与图像增强（亮度/对比度/饱和度/伽马）。

    图像质量由三层控制，按优先级排列：
    1. ISP 3A（rkaiq_3A_server）—— Rockchip 平台首选，自动曝光/白平衡
       rkaiq 必须在 root cgroup 中运行，否则 RT_GROUP_SCHED 会拒绝其线程创建
    2. V4L2 子设备手动控制（sensor_exposure / sensor_gain）—— 绕过 3A 的手动模式
    3. 软件增强（_enhance）—— 亮度/对比度/饱和度/伽马 + Gray World 自动白平衡
       在 macOS 等无 ISP 3A 的开发平台上作为主要图像调节手段
    """

    def __init__(
        self,
        index: int = 0,
        width: int = 1280,
        height: int = 720,
        brightness: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        gamma: float = 1.0,
        sensor_exposure: Optional[int] = None,
        sensor_gain: Optional[int] = None,
        auto_wb: bool = False,
        wb_strength: float = 0.5,
    ):
        self.index = index
        self.width = width
        self.height = height
        self.brightness = brightness
        self.contrast = contrast
        self.saturation = saturation
        self.gamma = gamma
        self.sensor_exposure = sensor_exposure      # 手动 sensor 曝光值 (行数)
        self.sensor_gain = sensor_gain              # 手动 sensor 模拟增益值
        self.auto_wb = auto_wb                      # 是否启用自动白平衡
        self.wb_strength = max(0.0, min(1.0, wb_strength))  # 白平衡强度 0~1
        self._sensor_subdev: Optional[str] = None   # sensor 子设备路径
        self._sensor_controls_applied = False
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

    def _find_sensor_subdev(self) -> Optional[str]:
        """查找带有 exposure 控制的 V4L2 子设备（sensor subdev）。
        仅在设置了 sensor_exposure 或 sensor_gain 时调用，用于手动模式绕过 3A。
        """
        if not self.sensor_exposure and not self.sensor_gain:
            return None
        for dev in sorted(glob.glob("/dev/v4l-subdev*")):
            try:
                result = subprocess.run(
                    ["v4l2-ctl", "-d", dev, "-C", "exposure"],
                    capture_output=True, text=True, timeout=2
                )
                if "exposure:" in result.stdout or "exposure:" in result.stderr:
                    logger.info(f"找到 sensor 子设备: {dev}")
                    return dev
            except Exception:
                continue
        return None

    def _apply_sensor_controls(self):
        """通过 V4L2 子设备手动设置 sensor 曝光和增益，绕过 ISP 3A。
        只在流启动后第一帧执行一次。设置后 3A 不再控制这些参数。
        """
        if self._sensor_controls_applied or self._sensor_subdev is None:
            return
        if self.sensor_exposure is None and self.sensor_gain is None:
            return
        try:
            cmd = ["v4l2-ctl", "-d", self._sensor_subdev]
            if self.sensor_exposure is not None:
                cmd += ["-c", f"exposure={self.sensor_exposure}"]
            if self.sensor_gain is not None:
                cmd += ["-c", f"analogue_gain={self.sensor_gain}"]
            subprocess.run(cmd, capture_output=True, timeout=2)
            self._sensor_controls_applied = True
            logger.info(
                f"sensor 控制已设置: exposure={self.sensor_exposure}, gain={self.sensor_gain}"
            )
        except Exception as e:
            logger.warning(f"设置 sensor 控制失败: {e}")

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
        self._sensor_subdev = self._find_sensor_subdev()
        self._sensor_controls_applied = False
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

        # 流启动后设置 sensor 曝光/增益（只在第一帧后设置，绕过 ISP 3A）
        if not self._sensor_controls_applied and self._sensor_subdev is not None:
            self._apply_sensor_controls()

        # 3. 软件图像增强（亮度/对比度/饱和度/伽马/AWB）
        #    在无 ISP 3A 的平台（如 macOS 开发机）上作为主要调节手段；
        #    在 RV1126 上，3A 已处理 AE/AWB，这里默认参数为 no-op
        # frame = self._enhance(frame)
        return frame

    def _enhance(self, frame: np.ndarray) -> np.ndarray:
        """软件图像增强：自动白平衡 / 亮度 / 对比度 / 饱和度 / 伽马校正。
        在无 ISP 3A 的平台上作为主要调节手段；在 RV1126 上所有参数默认为 no-op。
        """
        # 0. 自动白平衡 (Gray World)
        if self.auto_wb and self.wb_strength > 0:
            frame = self._apply_awb(frame)

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

    def _apply_awb(self, frame: np.ndarray) -> np.ndarray:
        """Gray World 自动白平衡"""
        # 计算各通道均值
        b_mean = frame[:, :, 0].mean()
        g_mean = frame[:, :, 1].mean()
        r_mean = frame[:, :, 2].mean()

        # 避免除零
        if g_mean < 1:
            return frame

        # 计算 gain 使 R 和 B 通道均值与 G 对齐
        r_gain = g_mean / max(r_mean, 1)
        b_gain = g_mean / max(b_mean, 1)

        # 限制 gain 范围，防止极端校正
        r_gain = max(0.5, min(2.0, r_gain))
        b_gain = max(0.5, min(2.0, b_gain))

        # 根据强度插值：1.0 = 无校正, gain = 目标增益
        r_gain = 1.0 + (r_gain - 1.0) * self.wb_strength
        b_gain = 1.0 + (b_gain - 1.0) * self.wb_strength

        # 应用增益
        frame = frame.astype(np.float32)
        frame[:, :, 0] *= b_gain
        frame[:, :, 2] *= r_gain
        frame = np.clip(frame, 0, 255).astype(np.uint8)

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
