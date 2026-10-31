"""Single-instance guard so two copies never fight over the desktop layer."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from core.logger import get_logger

log = get_logger("single-instance")
SERVER_NAME = "BlackWall.LiveWallpapers.SingleInstance"


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._server: QLocalServer | None = None
        self._socket: QLocalSocket | None = None

    def acquire(self, timeout_ms: int = 400) -> bool:
        """Return True if this is the first instance."""
        socket = QLocalSocket()
        socket.connectToServer(SERVER_NAME)
        if socket.waitForConnected(timeout_ms):
            socket.write(b"show")
            socket.flush()
            socket.waitForBytesWritten(timeout_ms)
            socket.disconnectFromServer()
            log.info("another BlackWall instance is running - asked it to show")
            return False

        self._server = QLocalServer(self)
        self._server.removeServer(SERVER_NAME)
        if not self._server.listen(SERVER_NAME):
            log.warning("could not start single-instance server: %s",
                        self._server.errorString())
            return True  # do not block the app if the socket cannot be created
        self._server.newConnection.connect(self._on_connection)
        return True

    def _on_connection(self) -> None:
        if self._server is None:
            return
        socket = self._server.nextPendingConnection()
        if socket is None:
            return
        socket.readyRead.connect(lambda: self._read(socket))
        socket.disconnected.connect(socket.deleteLater)
        # Data can arrive before readyRead is connected; wait briefly and read.
        from PySide6.QtCore import QTimer

        def check(sock=socket) -> None:
            try:
                if sock.bytesAvailable() == 0:
                    sock.waitForReadyRead(250)
            except RuntimeError:
                return
            self._read(sock)

        QTimer.singleShot(0, check)

    def _read(self, socket) -> None:  # noqa: ANN001
        data = bytes(socket.readAll())
        if b"show" in data:
            self.activated.emit()
