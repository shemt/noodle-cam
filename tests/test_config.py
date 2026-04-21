import json
import tempfile
import os
from pathlib import Path
from config.settings import Config, DEFAULT_CONFIG

def test_config_loads_defaults_when_file_missing():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "nonexistent.json")
        cfg = Config(path)
        assert cfg.get("camera.index") == 0
        assert cfg.get("vision.confidence_threshold") == 0.5

def test_config_persists_and_reloads():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = os.path.join(tmpdir, "config.json")
        cfg = Config(path)
        cfg.set("camera.index", 1)
        cfg.set("vision.customer_roi.x1", 100)
        cfg.save()

        cfg2 = Config(path)
        assert cfg2.get("camera.index") == 1
        assert cfg2.get("vision.customer_roi.x1") == 100

def test_config_nested_get_default():
    cfg = Config("/dev/null/nonexistent.json")
    assert cfg.get("vision.nonexistent_key", "fallback") == "fallback"
