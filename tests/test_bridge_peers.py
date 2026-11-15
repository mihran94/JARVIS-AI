"""The owner has to be able to reach the desktop over a private network.

The listener binds a private address and the phone reaches it over a VPN or
a tunnel. The peer address that may talk to the bridge is therefore the
owner's decision, and the loopback addresses always stay allowed.
"""
import os

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtWidgets import QApplication

from desktop.bridge_panel import BridgePanel
from remote.server import BridgeRequest, BridgeServer


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def a_request_from(address: str) -> BridgeRequest:
    return BridgeRequest(method='GET', path='/api/status', headers={}, body='',
                         remote_addr=address)


def test_the_loopback_addresses_are_always_allowed():
    server = BridgeServer.__new__(BridgeServer)
    server._allowed_hosts = ('127.0.0.1', '::1')
    server.set_allowed_hosts([])
    assert '127.0.0.1' in server._allowed_hosts
    assert '::1' in server._allowed_hosts


def test_the_owner_can_allow_a_vpn_or_tunnel_peer():
    server = BridgeServer.__new__(BridgeServer)
    server._allowed_hosts = ('127.0.0.1', '::1')
    server.set_allowed_hosts(['100.64.0.7'])
    assert '100.64.0.7' in server._allowed_hosts
    assert '127.0.0.1' in server._allowed_hosts


def test_an_empty_list_does_not_remove_the_loopback():
    server = BridgeServer.__new__(BridgeServer)
    server._allowed_hosts = ('127.0.0.1', '::1')
    server.set_allowed_hosts(['', '  '])
    assert set(server._allowed_hosts) == {'127.0.0.1', '::1'}


def test_the_panel_reads_the_peer_list(app, tmp_path):
    from tests.test_bridge_panel import make_panel
    _, panel = make_panel(tmp_path)
    panel.allowed_peers.setText('100.64.0.7, 10.0.0.4')
    peers = panel._allowed_peers()
    assert '100.64.0.7' in peers
    assert '10.0.0.4' in peers
    assert '127.0.0.1' in peers
    assert '::1' in peers


def test_the_panel_keeps_the_loopback_when_the_field_is_empty(app, tmp_path):
    from tests.test_bridge_panel import make_panel
    _, panel = make_panel(tmp_path)
    panel.allowed_peers.setText('')
    peers = panel._allowed_peers()
    assert '127.0.0.1' in peers
    assert '::1' in peers


def test_a_peer_that_is_not_allowed_is_refused():
    server = BridgeServer.__new__(BridgeServer)
    server._allowed_hosts = ('127.0.0.1', '::1')
    with pytest.raises(Exception):
        server._check_source(a_request_from('203.0.113.9'))


def test_a_peer_that_is_allowed_is_accepted():
    server = BridgeServer.__new__(BridgeServer)
    server._allowed_hosts = ('127.0.0.1', '::1')
    server.set_allowed_hosts(['100.64.0.7'])
    server._check_source(a_request_from('100.64.0.7'))


def test_the_listener_gives_the_connection_a_timeout():
    from remote.listener import ListenerConfig
    config = ListenerConfig(request_timeout_seconds=7.5)
    assert config.request_timeout_seconds == 7.5
