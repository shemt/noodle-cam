import time
import logging
from collections import deque
from typing import Dict, List

logger = logging.getLogger(__name__)


class BowlDetector:
    """多帧投票 + 防抖的碗位状态检测器"""

    def __init__(
        self,
        rois: List[Dict],
        vote_frames: int = 5,
        vote_threshold: int = 4,
        debounce: float = 2.0,
    ):
        self.rois = rois
        self.vote_frames = vote_frames
        self.vote_threshold = vote_threshold
        self.debounce = debounce

        self.histories: Dict[int, deque] = {
            r["id"]: deque(maxlen=vote_frames) for r in rois
        }
        self.confirmed_states: Dict[int, bool] = {r["id"]: False for r in rois}
        self.last_change_time: Dict[int, float] = {r["id"]: 0 for r in rois}

    def update(self, detections: List[Dict]) -> List[Dict]:
        now = time.time()
        events = []

        for roi in self.rois:
            rid = roi["id"]
            has_bowl = self._check_roi(roi, detections)
            self.histories[rid].append(has_bowl)

            if len(self.histories[rid]) < self.vote_frames:
                continue

            true_count = sum(self.histories[rid])
            false_count = self.vote_frames - true_count

            new_state = None
            if true_count >= self.vote_threshold:
                new_state = True
            elif false_count >= self.vote_threshold:
                new_state = False
            else:
                continue

            if new_state != self.confirmed_states[rid]:
                if now - self.last_change_time[rid] >= self.debounce:
                    old_state = self.confirmed_states[rid]
                    self.confirmed_states[rid] = new_state
                    self.last_change_time[rid] = now
                    event_name = "placed" if new_state else "removed"
                    logger.info(f"碗位 {rid} 状态变化: {old_state} -> {new_state}")
                    events.append(
                        {
                            "bowl_id": rid,
                            "event": event_name,
                            "old_state": old_state,
                            "new_state": new_state,
                            "timestamp": now,
                        }
                    )
        return events

    def update_rois(self, rois: List[Dict]):
        """动态更新碗位 ROI 列表，保留已有碗位的历史数据，清理已删除碗位"""
        new_ids = {r["id"] for r in rois}
        old_ids = set(self.confirmed_states.keys())

        # 移除已不存在的碗位
        for rid in old_ids - new_ids:
            self.histories.pop(rid, None)
            self.confirmed_states.pop(rid, None)
            self.last_change_time.pop(rid, None)

        # 新增碗位
        for r in rois:
            rid = r["id"]
            if rid not in self.histories:
                self.histories[rid] = deque(maxlen=self.vote_frames)
                self.confirmed_states[rid] = False
                self.last_change_time[rid] = 0

        self.rois = rois

    def get_states(self) -> Dict[int, bool]:
        """返回各碗位当前确认状态的副本"""
        return self.confirmed_states.copy()

    def any_bowl_present(self) -> bool:
        """是否有至少一个碗位确认存在碗"""
        return any(self.confirmed_states.values())

    def _check_roi(self, roi: Dict, detections: List[Dict]) -> bool:
        for det in detections:
            if det.get("class") == "bowl":
                x1, y1, x2, y2 = det["bbox"]
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                if roi["x1"] <= cx <= roi["x2"] and roi["y1"] <= cy <= roi["y2"]:
                    return True
        return False
