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

# COCO 80 类名称
COCO_NAMES = [
    'person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 'traffic light',
    'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow',
    'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee',
    'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard',
    'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple',
    'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch',
    'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone',
    'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear',
    'hair drier', 'toothbrush'
]

# YOLOv5 默认 anchor
ANCHORS = [
    [[10, 13], [16, 30], [33, 23]],       # P3/8
    [[30, 61], [62, 45], [59, 119]],      # P4/16
    [[116, 90], [156, 198], [373, 326]],  # P5/32
]
STRIDES = [8, 16, 32]


class YOLODetector:
    """YOLO 目标检测封装，优先 RKNN NPU，fallback 到 ONNX/OpenCV DNN"""

    def __init__(self, model_path: str, confidence: float = 0.5, input_size: int = 640):
        self.model_path = Path(model_path)
        self.confidence = confidence
        self.input_size = input_size
        self._rknn = None
        self._net = None
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
        # 预处理: BGR -> RGB, resize, uint8, HWC->CHW, add batch
        img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_size, self.input_size))
        img = img.astype(np.uint8)
        img = np.transpose(img, (2, 0, 1))
        img = np.expand_dims(img, axis=0)

        try:
            outputs = self._rknn.inference(inputs=[img])
        except Exception as e:
            logger.error(f"RKNN 推理异常: {e}")
            return []

        return self._parse_yolov5_outputs(outputs, frame.shape)

    def _detect_opencv(self, frame: np.ndarray) -> List[Dict]:
        blob = cv2.dnn.blobFromImage(frame, 1 / 255.0, (self.input_size, self.input_size), swapRB=True, crop=False)
        self._net.setInput(blob)
        outputs = self._net.forward(self._net.getUnconnectedOutLayersNames())
        return self._parse_yolo_outputs(outputs, frame.shape)

    def _parse_yolov5_outputs(self, outputs, orig_shape) -> List[Dict]:
        """YOLOv5 RKNN 输出解析: 3 个尺度 (1, 255, H, W)"""
        if not outputs or len(outputs) != 3:
            return []

        h, w = orig_shape[:2]
        all_dets = []

        def sigmoid(z):
            return 1.0 / (1.0 + np.exp(-z))

        for idx, (output, anchor, stride) in enumerate(zip(outputs, ANCHORS, STRIDES)):
            arr = np.array(output) if isinstance(output, list) else output
            batch, c, grid_h, grid_w = arr.shape
            na = 3      # num anchors
            nc = 80     # num classes (COCO)

            # (1, 255, H, W) -> (1, 3, 85, H, W) -> (1, 3, H, W, 85)
            x = arr.reshape(batch, na, 5 + nc, grid_h, grid_w)
            x = np.transpose(x, (0, 1, 3, 4, 2))

            # grid offsets
            grid_y, grid_x = np.meshgrid(np.arange(grid_h), np.arange(grid_w), indexing='ij')
            grid_x = grid_x.reshape(1, 1, grid_h, grid_w)
            grid_y = grid_y.reshape(1, 1, grid_h, grid_w)

            # decode xywh
            x[..., 0:2] = sigmoid(x[..., 0:2])
            x[..., 0] = (x[..., 0] + grid_x) / grid_w
            x[..., 1] = (x[..., 1] + grid_y) / grid_h

            anchor_t = np.array(anchor).reshape(1, na, 1, 1, 2)
            x[..., 2:4] = np.exp(np.clip(x[..., 2:4], -50, 50)) * anchor_t / self.input_size

            # sigmoid conf and cls
            x[..., 4:] = sigmoid(x[..., 4:])

            # flatten to (N, 85)
            x = x.reshape(-1, 5 + nc)

            obj_conf = x[:, 4]
            mask = obj_conf > self.confidence
            if not mask.any():
                continue

            x = x[mask]
            obj_conf = x[:, 4:5]
            cls_scores = x[:, 5:]
            cls_conf = cls_scores.max(axis=1, keepdims=True)
            cls_id = cls_scores.argmax(axis=1, keepdims=True)

            scores = obj_conf * cls_conf
            mask2 = scores.flatten() > self.confidence
            if not mask2.any():
                continue

            x = x[mask2]
            scores = scores[mask2].flatten()
            cls_id = cls_id[mask2].flatten()

            # convert normalized xyxy to pixel coords
            cx, cy, bw, bh = x[:, 0], x[:, 1], x[:, 2], x[:, 3]
            x1 = (cx - bw / 2) * w
            y1 = (cy - bh / 2) * h
            x2 = (cx + bw / 2) * w
            y2 = (cy + bh / 2) * h

            dets = np.stack([x1, y1, x2, y2, scores, cls_id], axis=1)
            all_dets.append(dets)

        if not all_dets:
            return []

        dets = np.concatenate(all_dets, axis=0)

        # NMS
        keep = self._nms(dets[:, :4], dets[:, 4])
        dets = dets[keep]

        # filter: only keep person(0) and bowl(45)
        interested = {0: "person", 45: "bowl"}
        results = []
        for d in dets:
            x1, y1, x2, y2, conf, cid = d
            cid = int(cid)
            if cid not in interested:
                continue
            results.append({
                "class": interested[cid],
                "bbox": [max(0, int(x1)), max(0, int(y1)), min(w, int(x2)), min(h, int(y2))],
                "conf": round(float(conf), 3),
            })

        if results:
            logger.debug(f"检测到 {len(results)} 个目标")
        return results

    def _parse_yolo_outputs(self, outputs, orig_shape) -> List[Dict]:
        """OpenCV DNN YOLO 输出解析 (YOLOv5 ONNX: Nx25200x85)"""
        h, w = orig_shape[:2]
        detections = []
        for output in outputs:
            arr = np.array(output)
            # 处理 batch 维: (1, 25200, 85) -> (25200, 85)
            if arr.ndim == 3:
                arr = arr.reshape(-1, arr.shape[-1])
            for det in arr:
                scores = det[5:]
                class_id = int(np.argmax(scores))
                class_score = float(scores[class_id])
                objectness = float(det[4])
                confidence = objectness * class_score
                if confidence < self.confidence:
                    continue
                # YOLOv5 ONNX xywh 是模型输入空间 (640x640) 下的像素坐标
                cx, cy, bw, bh = det[0:4]
                x1 = int((cx - bw / 2) * w / self.input_size)
                y1 = int((cy - bh / 2) * h / self.input_size)
                x2 = int((cx + bw / 2) * w / self.input_size)
                y2 = int((cy + bh / 2) * h / self.input_size)
                name = COCO_NAMES[class_id] if class_id < len(COCO_NAMES) else f"cls_{class_id}"
                detections.append({
                    "class": name,
                    "bbox": [max(0, x1), max(0, y1), min(w, x2), min(h, y2)],
                    "conf": round(confidence, 3),
                })
        return self._nms_dict(detections)

    def _nms(self, boxes: np.ndarray, scores: np.ndarray, iou_thresh: float = 0.45) -> List[int]:
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size > 0:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
            order = order[1:][iou <= iou_thresh]
        return keep

    def _nms_dict(self, detections: List[Dict], iou_thresh: float = 0.45) -> List[Dict]:
        if not detections:
            return detections
        detections = sorted(detections, key=lambda x: x["conf"], reverse=True)
        kept = []
        for det in detections:
            x1, y1, x2, y2 = det["bbox"]
            area = (x2 - x1) * (y2 - y1)
            suppressed = False
            for k in kept:
                kx1, ky1, kx2, ky2 = k["bbox"]
                ix1, iy1 = max(x1, kx1), max(y1, ky1)
                ix2, iy2 = min(x2, kx2), min(y2, ky2)
                inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                union = area + (kx2 - kx1) * (ky2 - ky1) - inter
                iou = inter / union if union > 0 else 0
                if iou > iou_thresh and det["class"] == k["class"]:
                    suppressed = True
                    break
            if not suppressed:
                kept.append(det)
        return kept

    def release(self):
        if self._rknn is not None:
            self._rknn.release()
            self._rknn = None
