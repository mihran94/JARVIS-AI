import pytest
from remote.private_tunnel import private_origin


def config():
    return {'TCP': {'443': {'HTTPS': True}}, 'Web': {
        'desktop.example.ts.net:443': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8765'}}}}}


def test_verified_private_route():
    assert private_origin(config()) == 'https://desktop.example.ts.net'


@pytest.mark.parametrize('change', ['funnel', 'public_host', 'wrong_port', 'no_https'])
def test_do_not_enable_plaintext_for_unverified_route(change):
    value = config()
    if change == 'funnel': value['AllowFunnel'] = {'desktop.example.ts.net:443': True}
    if change == 'public_host': value['Web']['public.example.com:443'] = value['Web'].pop('desktop.example.ts.net:443')
    if change == 'wrong_port': value['Web']['desktop.example.ts.net:443']['Handlers']['/']['Proxy'] = 'http://0.0.0.0:8765'
    if change == 'no_https': value['TCP']['443']['HTTPS'] = False
    with pytest.raises(ValueError): private_origin(value)


def test_startup_is_opt_in_and_only_binds_loopback(tmp_path, monkeypatch):
    from test_bridge_panel import make_panel
    app, panel = make_panel(tmp_path)
    starts = []
    monkeypatch.setattr(panel.listener, 'start', lambda: starts.append(panel.listener._config))
    monkeypatch.setattr('remote.private_tunnel.discover_private_origin', lambda: 'https://desktop.example.ts.net')
    try:
        assert not panel.restore_private_listener()
        assert starts == []
        panel.store.set('bridge:private_startup', True)
        assert panel.restore_private_listener()
        assert len(starts) == 1
        assert starts[0].host == '127.0.0.1' and starts[0].port == 8765
        assert starts[0].allow_plaintext and not starts[0].allow_public_bind
        assert panel.phone_address.text() == 'https://desktop.example.ts.net'
        panel.policy.stop()
        assert not panel.restore_private_listener()
        assert len(starts) == 1
    finally:
        panel.close()
        panel.deleteLater()
        app.processEvents()
