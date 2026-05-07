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

        recent = list(self.history)[-5:]
        first_positive = next((a for a in recent if a > 0), 0)
        last_positive = next((a for a in reversed(recent) if a > 0), 0)

        if first_positive > 0 and last_positive / first_positive >= self.area_growth_threshold:
            if now - self.last_trigger_time >= self.cooldown:
                self.last_trigger_time = now
                logger.info("检测到客户由远及近靠近")
                return True
        return False

    def set_roi(self, roi: dict):
        """动态更新客户检测区 ROI"""
        self.roi = roi

    def _in_roi(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        return (self.roi.get("x1", 0) <= cx <= self.roi.get("x2", 1920) and
                self.roi.get("y1", 0) <= cy <= self.roi.get("y2", 1080))
