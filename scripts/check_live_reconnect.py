"""Bounded loopback reconnect probe; no microphone, credentials or cloud calls."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication, QEvent, QUrl
from PySide6.QtNetwork import QHostAddress
from PySide6.QtWebSockets import QWebSocket, QWebSocketServer

from desktop.live_voice import LiveVoice


def main():
    app = QCoreApplication([])
    server = QWebSocketServer('JARVIS loopback reconnect', QWebSocketServer.SslMode.NonSecureMode)
    if not server.listen(QHostAddress.SpecialAddress.LocalHost, 0):
        raise RuntimeError('Could not bind loopback test listener.')
    live = LiveVoice()
    peers, recoveries = [], []

    class SilentPlayer:
        def reset(self):
            pass

        def deleteLater(self):
            pass

    def connect():
        live.player = SilentPlayer()
        socket = live.socket = QWebSocket(parent=live)
        socket.disconnected.connect(live.connection_lost)
        socket.errorOccurred.connect(live.connection_lost)
        socket.connected.connect(lambda: live.set_state('listening'))
        live.set_state('connecting')
        socket.open(QUrl(f'ws://127.0.0.1:{server.serverPort()}'))

    def recover():
        recoveries.append(True)
        connect()

    def wait_for(condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        if not condition():
            raise RuntimeError(f'Loopback connection timed out: peers={len(peers)}, state={live.state}')

    server.newConnection.connect(lambda: peers.append(server.nextPendingConnection()))
    live.reconnect_requested.connect(recover)
    try:
        connect()
        wait_for(lambda: len(peers) == 1 and live.state == 'listening')
        peers[0].abort()
        wait_for(lambda: len(peers) == 2 and live.state == 'listening')
        if recoveries != [True]:
            raise RuntimeError('Expected exactly one recovery request.')
        print(json.dumps({'connections': len(peers), 'recoveries': len(recoveries),
                          'state': live.state, 'transport': 'loopback WebSocket'}))
    finally:
        live.stop()
        for peer in peers:
            peer.abort()
            peer.deleteLater()
        server.close()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


if __name__ == '__main__':
    main()
