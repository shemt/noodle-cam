import os
import asyncio
import threading
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_MESSAGES = {
    "customer_approach": "请拿碗放在碗托上",
    "meal_ready": "您的餐已准备好，请取餐",
    "bowl_placed": "已检测到放碗",
    "bowl_removed": "碗已取走，请慢用",
}


class TTSPlayer:
    """语音播报：通过 edge-tts 预合成音频后播放"""

    def __init__(
        self,
        volume: int = 80,
        audio_dir: str = "audio_clips",
        messages: Optional[Dict[str, str]] = None,
        voice: str = "zh-CN-XiaoxiaoNeural",
    ):
        self.volume = max(0, min(100, volume))
        self.audio_dir = Path(audio_dir)
        self.messages = messages or DEFAULT_MESSAGES.copy()
        self.voice = voice
        self._lock = threading.Lock()
        self._pre_synthesized: Dict[str, Path] = {}
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def pre_synthesize(self):
        """启动时预合成所有配置的文字为音频文件"""
        for key, text in self.messages.items():
            wav_path = self._get_wav_path(key)
            if wav_path.exists():
                self._pre_synthesized[key] = wav_path
                logger.info(f"音频已存在: {key} -> {wav_path}")
                continue
            try:
                self._synthesize_text(text, wav_path)
                self._pre_synthesized[key] = wav_path
                logger.info(f"预合成成功: {key} -> {wav_path}")
            except Exception as e:
                logger.error(f"预合成失败 [{key}]: {e}")

    def say(self, key: str):
        """根据 key 播放对应的语音"""
        with self._lock:
            if key in self._pre_synthesized:
                self._play_file(self._pre_synthesized[key])
                return

            text = self.messages.get(key)
            if not text:
                logger.warning(f"未知播报 key: {key}")
                return

            wav_path = self._get_wav_path(key)
            try:
                self._synthesize_text(text, wav_path)
                self._pre_synthesized[key] = wav_path
                self._play_file(wav_path)
            except Exception as e:
                logger.error(f"实时合成播放失败 [{key}]: {e}")

    def update_messages(self, messages: Dict[str, str]):
        """更新播报文字配置，重新预合成"""
        self.messages = messages
        self._pre_synthesized.clear()
        self.pre_synthesize()

    def _get_wav_path(self, key: str) -> Path:
        return self.audio_dir / f"{key}.wav"

    def _synthesize_text(self, text: str, output_path: Path):
        """使用 edge-tts 合成音频并转为 wav"""
        try:
            import edge_tts
        except ImportError:
            raise RuntimeError("edge-tts 未安装，无法合成语音")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_mp3 = tmp.name

        try:
            # 异步运行 edge-tts
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                communicate = edge_tts.Communicate(text, voice=self.voice)
                loop.run_until_complete(communicate.save(tmp_mp3))
            finally:
                loop.close()

            # ffmpeg 转为 wav
            cmd = [
                "ffmpeg", "-y", "-i", tmp_mp3,
                "-ac", "1", "-ar", "22050",
                str(output_path)
            ]
            result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            if result.returncode != 0:
                raise RuntimeError(f"ffmpeg 转换失败: {result.returncode}")
        finally:
            try:
                os.unlink(tmp_mp3)
            except OSError:
                pass

    def _play_file(self, path: Path):
        try:
            # 使用 aplay 播放，通过 amixer 调整音量
            subprocess.run(
                ["aplay", "-q", str(path)],
                check=True, timeout=30
            )
            logger.info(f"播放音频: {path}")
        except Exception as e:
            logger.error(f"播放音频失败: {e}")
