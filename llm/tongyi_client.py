import json
import base64
import logging
from typing import Dict, List, Optional

import numpy as np

try:
    import dashscope
    from dashscope import MultiModalConversation
except ImportError:
    dashscope = None

logger = logging.getLogger(__name__)


class TongyiClient:
    """通义千问多模态视觉理解封装，含自动降级策略"""

    def __init__(self, api_key: str, model: str = "qwen-vl-plus", fallback_threshold: float = 0.3):
        self.api_key = api_key
        self.model = model
        self.fallback_threshold = fallback_threshold
        self._fail_count = 0
        self._max_fail = 3
        self._backoff_until = 0
        if dashscope:
            dashscope.api_key = api_key

    def is_available(self) -> bool:
        import time
        if self._fail_count >= self._max_fail:
            if time.time() < self._backoff_until:
                return False
            self._fail_count = 0
        return dashscope is not None and bool(self.api_key)

    def analyze_frame(self, frame: np.ndarray, prompt: str = None) -> Optional[Dict]:
        if not self.is_available():
            return None

        try:
            import cv2
            import time
            _, buf = cv2.imencode(".jpg", frame)
            b64 = base64.b64encode(buf).decode("utf-8")

            system_prompt = (
                "你是一个面馆机器人视觉助手。请分析图片并返回严格的 JSON 格式："
                '{"customer_nearby": bool, "bowls": [{"id": int, "present": bool}], "confidence": float}'
            )
            user_prompt = prompt or "检测画面中是否有顾客靠近，以及每个碗位是否有碗。"

            messages = [
                {"role": "system", "content": [{"text": system_prompt}]},
                {"role": "user", "content": [
                    {"image": f"data:image/jpeg;base64,{b64}"},
                    {"text": user_prompt}
                ]}
            ]

            response = MultiModalConversation.call(model=self.model, messages=messages)
            content = response.output.choices[0].message.content
            text = content[0]["text"] if isinstance(content, list) else content

            json_start = text.find("{")
            json_end = text.rfind("}") + 1
            result = json.loads(text[json_start:json_end])

            self._fail_count = 0
            logger.info(f"通义千问识别结果: {result}")
            return result

        except Exception as e:
            self._fail_count += 1
            if self._fail_count >= self._max_fail:
                self._backoff_until = time.time() + 1800
                logger.warning("通义千问连续失败 3 次，进入 30 分钟冷却")
            else:
                logger.warning(f"通义千问调用失败 ({self._fail_count}/{self._max_fail}): {e}")
            return None
