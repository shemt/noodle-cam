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
