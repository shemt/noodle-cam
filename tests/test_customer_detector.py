from vision.customer_detector import CustomerDetector


def test_no_trigger_when_no_person():
    det = CustomerDetector({"x1": 0, "y1": 0, "x2": 640, "y2": 480})
    assert det.update([]) is False
    assert det.update([]) is False


def test_no_trigger_when_person_stays_same_size():
    det = CustomerDetector({"x1": 0, "y1": 0, "x2": 640, "y2": 480})
    for _ in range(10):
        result = det.update([{"class": "person", "bbox": [100, 100, 200, 200]}])
    assert result is False


def test_trigger_when_person_grows_significantly():
    det = CustomerDetector({"x1": 0, "y1": 0, "x2": 640, "y2": 480}, history_size=10, area_growth_threshold=1.3)
    for _ in range(5):
        det.update([{"class": "person", "bbox": [100, 100, 110, 110]}])
    result = det.update([{"class": "person", "bbox": [100, 100, 250, 250]}])
    assert result is True


def test_cooldown_prevents_double_trigger():
    det = CustomerDetector({"x1": 0, "y1": 0, "x2": 640, "y2": 480}, history_size=10, area_growth_threshold=1.3, cooldown=5.0)
    for _ in range(5):
        det.update([{"class": "person", "bbox": [100, 100, 110, 110]}])
    assert det.update([{"class": "person", "bbox": [100, 100, 250, 250]}]) is True
    assert det.update([{"class": "person", "bbox": [100, 100, 250, 250]}]) is False
