import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class RTSPStreamer:
    """GStreamer RTSP 服务器，通过 appsrc 从主程序接收帧，局域网可直接拉流观看"""

    def __init__(
        self,
        fps: int = 15,
        width: int = 640,
        height: int = 480,
        bitrate: int = 500,
        port: int = 8554,
        path: str = "/live",
    ):
        self.fps = fps
        self.width = width
        self.height = height
        self.bitrate = bitrate
        self.port = port
        self.path = path
        self._server = None
        self._loop = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._appsrc = None

    def start(self):
        if self._running:
            logger.warning("RTSP 服务器已在运行")
            return

        try:
            import gi
            gi.require_version("Gst", "1.0")
            gi.require_version("GstRtspServer", "1.0")
            from gi.repository import Gst, GstRtspServer, GLib
        except ImportError as e:
            logger.error(f"GStreamer RTSP 依赖缺失: {e}")
            return

        Gst.init(None)

        self._server = GstRtspServer.RTSPServer.new()
        self._server.set_service(str(self.port))

        factory = GstRtspServer.RTSPMediaFactory.new()
        # 使用 appsrc 从主程序接收 BGR 帧
        pipeline = (
            "appsrc name=mysrc is-live=true format=time do-timestamp=true ! "
            "videoconvert ! video/x-raw,format=I420 ! "
            f"x264enc tune=zerolatency bitrate={self.bitrate} speed-preset=ultrafast "
            f"key-int-max={self.fps * 2} ! "
            "rtph264pay name=pay0 pt=96"
        )
        factory.set_launch(pipeline)
        factory.set_shared(True)
        factory.connect("media-configure", self._on_media_configure)

        mounts = self._server.get_mount_points()
        mounts.add_factory(self.path, factory)

        self._server.attach(None)
        rtsp_url = f"rtsp://0.0.0.0:{self.port}{self.path}"
        logger.info(f"RTSP 服务器已启动: {rtsp_url}")
        logger.info(f"局域网观看地址: rtsp://<设备IP>:{self.port}{self.path}")

        self._loop = GLib.MainLoop()
        self._running = True
        self._thread = threading.Thread(target=self._loop.run, daemon=True)
        self._thread.start()

    def _on_media_configure(self, factory, media):
        import gi
        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        element = media.get_element()
        self._appsrc = element.get_by_name("mysrc")
        caps_str = (
            f"video/x-raw,format=BGR,width={self.width},height={self.height},"
            f"framerate={self.fps}/1"
        )
        caps = Gst.Caps.from_string(caps_str)
        self._appsrc.set_property("caps", caps)
        logger.info(f"appsrc 已配置: {self.width}x{self.height}@{self.fps}fps BGR")

    def push_frame(self, frame):
        if self._appsrc is None:
            return
        try:
            import gi
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst

            data = frame.tobytes()
            buf = Gst.Buffer.new_wrapped(data)
            self._appsrc.emit("push-buffer", buf)
        except Exception as e:
            logger.debug(f"推送帧失败: {e}")

    def stop(self):
        if not self._running:
            return
        self._running = False
        if self._loop:
            self._loop.quit()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("RTSP 服务器已停止")
