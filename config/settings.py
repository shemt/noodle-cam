import json
import os
from pathlib import Path
from typing import Dict, Any

DEFAULT_CONFIG = {
    "camera": {"index": 0, "width": 1280, "height": 720},
    "vision": {
        "model_path": "models/yolov5s.rknn",
        "confidence_threshold": 0.5,
        "customer_roi": {"x1": 0, "y1": 0, "x2": 640, "y2": 480},
        "bowl_rois": [],
        "vote_frames": 5,
        "vote_threshold": 4,
        "debounce_seconds": 2.0,
    },
    "audio": {"volume": 80, "pre_recorded": True, "audio_dir": "audio_clips"},
    "backend": {"url": "http://localhost:5000", "heartbeat_interval": 30},
    "video": {
        "rtsp_enabled": True,
        "rtsp_fps": 1,
        "record_enabled": True,
        "record_dir": "recordings",
        "max_storage_gb": 2,
    },
    "llm": {"enabled": False, "api_key": "", "fallback_threshold": 0.3, "model": "qwen-vl-plus"},
    "web": {"host": "0.0.0.0", "port": 8080},
}


class Config:
    def __init__(self, path: str = "config.json"):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                return self._deep_merge(DEFAULT_CONFIG.copy(), loaded)
            except (json.JSONDecodeError, IOError):
                pass
        return DEFAULT_CONFIG.copy()

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                base[key] = self._deep_merge(base[key], value)
            else:
                base[key] = value
        return base

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default=None):
        keys = key.split(".")
        d = self.data
        for k in keys:
            if isinstance(d, dict) and k in d:
                d = d[k]
            else:
                return default
        return d

    def set(self, key: str, value):
        keys = key.split(".")
        d = self.data
        for k in keys[:-1]:
            if k not in d:
                d[k] = {}
            d = d[k]
        d[keys[-1]] = value
