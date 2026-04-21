import os
import tempfile
import time
from pathlib import Path
from video.recorder import VideoRecorder


def test_cleanup_deletes_oldest_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = VideoRecorder(tmpdir, max_storage_gb=0.0001)  # ~100KB
        old = Path(tmpdir) / "noodlecam_old.mp4"
        old.write_bytes(b"x" * 60000)
        time.sleep(0.1)
        new = Path(tmpdir) / "noodlecam_new.mp4"
        new.write_bytes(b"x" * 60000)
        rec._cleanup_if_needed()
        assert not old.exists()
        assert new.exists()


def test_stop_returns_file_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        rec = VideoRecorder(tmpdir, max_storage_gb=2)
        rec.current_file = Path(tmpdir) / "test.mp4"
        rec.current_process = None
        path = rec.stop()
        assert path is None
