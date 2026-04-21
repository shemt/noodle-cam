import os
import threading
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TTSPlayer:
    """语音播报：优先预录音频，fallback 到 pyttsx3 本地合成"""

    def __init__(self, volume: int = 80, use_pre_recorded: bool = True, audio_dir: str = "audio_clips"):
        self.volume = max(0, min(100, volume))
        self.use_pre_recorded = use_pre_recorded
        self.audio_dir = audio_dir
        self._lock = threading.Lock()
        os.makedirs(audio_dir, exist_ok=True)

    def play(self, text: str, audio_file: Optional[str] = None):
        with self._lock:
            if audio_file and os.path.exists(audio_file):
                real = os.path.realpath(audio_file)
                base = os.path.realpath(self.audio_dir)
                if not real.startswith(base + os.sep) and real != base:
                    logger.warning(f"拒绝播放 audio_dir 外的文件: {audio_file}")
                    return
                self._play_file(audio_file)
                return
            if self.use_pre_recorded:
                pre = os.path.join(self.audio_dir, f"{text}.wav")
                if os.path.exists(pre):
                    self._play_file(pre)
                    return
            self._synthesize_and_play(text)

    def _play_file(self, path: str):
        try:
            import subprocess
            subprocess.run(["aplay", "-q", path], check=True, timeout=10)
            logger.debug(f"播放音频: {path}")
        except Exception as e:
            logger.error(f"播放音频失败: {e}")

    def _synthesize_and_play(self, text: str):
        try:
            import pyttsx3
            engine = pyttsx3.init()
            engine.setProperty('volume', self.volume / 100.0)
            engine.say(text)
            engine.runAndWait()
            logger.info(f"TTS 播报: {text}")
        except Exception as e:
            logger.error(f"TTS 失败: {e}")
