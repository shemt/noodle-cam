import time
import threading
import logging
from typing import Dict, Any, Optional, Callable
from queue import Queue

import requests

logger = logging.getLogger(__name__)


class BackendClient:
    """后台 HTTP 通信客户端，支持事件队列缓存和心跳"""

    def __init__(self, base_url: str, heartbeat_interval: int = 30):
        self.base_url = base_url.rstrip("/")
        self.heartbeat_interval = heartbeat_interval
        self._queue = Queue()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._callbacks: Dict[str, Callable] = {}

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()
        logger.info("后台通信线程已启动")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            logger.info("后台通信线程已停止")

    def register_callback(self, endpoint: str, handler: Callable):
        self._callbacks[endpoint] = handler

    def send_bowl_status(self, event: Dict[str, Any]):
        self._post("/device/bowl_status", event)

    def send_customer_detected(self, data: Dict[str, Any]):
        self._post("/device/customer_detected", data)

    def send_heartbeat(self, data: Dict[str, Any]):
        self._post("/device/heartbeat", data)

    def send_video_clip(self, data: Dict[str, Any]):
        self._post("/device/video_clip", data)

    def _post(self, endpoint: str, payload: Dict[str, Any], retry: bool = True):
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            logger.debug(f"POST {endpoint} 成功")
        except Exception as e:
            logger.warning(f"POST {endpoint} 失败: {e}")
            if retry:
                self._queue.put(("post", endpoint, payload))

    def _worker(self):
        last_hb = time.time() if self.heartbeat_interval > 0 else None
        while self._running:
            while not self._queue.empty():
                _, endpoint, payload = self._queue.get()
                self._post(endpoint, payload)

            if self.heartbeat_interval > 0 and last_hb is not None:
                now = time.time()
                if now - last_hb >= self.heartbeat_interval:
                    self._post("/device/heartbeat", {"timestamp": now, "status": "ok", "mode": "local"}, retry=False)
                    last_hb = now

            time.sleep(1)
