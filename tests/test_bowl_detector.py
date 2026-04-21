from vision.bowl_detector import BowlDetector


def test_no_event_on_empty_history():
    det = BowlDetector([{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}])
    events = det.update([])
    assert events == []


def test_placed_event_after_consistent_votes():
    det = BowlDetector(
        [{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}],
        vote_frames=3,
        vote_threshold=3,
    )
    events = []
    for _ in range(3):
        events = det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    assert len(events) == 1
    assert events[0]["event"] == "placed"
    assert events[0]["bowl_id"] == 1


def test_no_event_with_mixed_votes():
    det = BowlDetector(
        [{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}],
        vote_frames=3,
        vote_threshold=3,
    )
    det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    det.update([])
    events = det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    assert events == []


def test_debounce_prevents_rapid_flip():
    det = BowlDetector(
        [{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}],
        vote_frames=2,
        vote_threshold=2,
        debounce=1.0,
    )
    det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    events = det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    assert len(events) == 1
    events = det.update([])
    events = det.update([])
    assert events == []


def test_removed_event_after_debounce():
    import time

    det = BowlDetector(
        [{"id": 1, "x1": 0, "y1": 0, "x2": 100, "y2": 100}],
        vote_frames=2,
        vote_threshold=2,
        debounce=0.05,
    )
    det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    det.update([{"class": "bowl", "bbox": [10, 10, 30, 30]}])
    time.sleep(0.06)
    det.update([])
    events = det.update([])
    assert len(events) == 1
    assert events[0]["event"] == "removed"
