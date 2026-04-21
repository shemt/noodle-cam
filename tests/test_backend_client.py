import pytest
from unittest.mock import patch, MagicMock
from comm.backend_client import BackendClient

def test_send_bowl_status_makes_post_request():
    client = BackendClient("http://localhost:5000", heartbeat_interval=60)
    with patch("comm.backend_client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        client.send_bowl_status({"bowl_id": 1, "event": "placed"})
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "http://localhost:5000/device/bowl_status"

def test_failed_request_is_queued_for_retry():
    client = BackendClient("http://localhost:5000", heartbeat_interval=60)
    with patch("comm.backend_client.requests.post") as mock_post:
        mock_post.side_effect = Exception("connection error")
        client.send_bowl_status({"bowl_id": 1, "event": "placed"})
        assert client._queue.qsize() == 1

def test_heartbeat_sent_periodically():
    client = BackendClient("http://localhost:5000", heartbeat_interval=0.1)
    with patch("comm.backend_client.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        client.start()
        import time
        time.sleep(0.25)
        client.stop()
        assert mock_post.call_count >= 1
