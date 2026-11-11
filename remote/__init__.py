"""Versioned desktop/mobile bridge for JARVIS AI.

The mobile client lives in `mihran94/jarvis-blue-android`
(`core/windows/BridgeClient.kt`). This package is the desktop half of the same
protocol and must stay byte compatible with it.

Nothing in this package opens a network socket. `remote.server.BridgeServer`
only decides what a signed request means; binding, TLS and the private tunnel
remain an operator decision.
"""
from remote.pairing import Pairing, PairingError, PairingStore, PairedDevice
from remote.protocol import (
    KEY_ID,
    PROTOCOL_VERSION,
    ProtocolError,
    canonical_string,
    check_timestamp,
    sha256_hex,
    sign,
    verify,
)
from remote.replay import ReplayGuard
from remote.server import BridgeHandlerError, BridgeRequest, BridgeResponse, BridgeServer

__all__ = [
    'BridgeHandlerError',
    'BridgeRequest',
    'BridgeResponse',
    'BridgeServer',
    'KEY_ID',
    'PROTOCOL_VERSION',
    'Pairing',
    'PairingError',
    'PairingStore',
    'PairedDevice',
    'ProtocolError',
    'ReplayGuard',
    'canonical_string',
    'check_timestamp',
    'sha256_hex',
    'sign',
    'verify',
]
