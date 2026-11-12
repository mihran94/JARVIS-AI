"""The pairing code that the desktop shows and the iPhone scans.

The code is a short text block:

    JARVIS-BRIDGE-v1
    bridge=https://pc.example.lan:8765
    key=jarvis-iphone-v1
    secret=<the one time secret>
    expires=1764000000

The desktop draws it as a QR code and the phone reads it with the camera. The
same text can be pasted, which is what a person does when the camera is not
usable.

The format is fixed by `iphone-pwa/js/pairing.js` on the phone side, and the
two are checked against each other by the test suite.
"""
import time

#: The first line of every pairing code.
PAIRING_FORMAT = 'JARVIS-BRIDGE-v1'

#: How long a pairing code stays usable, in seconds.
DEFAULT_LIFETIME_SECONDS = 900

#: The shortest secret the bridge accepts.
MINIMUM_SECRET_LENGTH = 32


class PairingCodeError(ValueError):
    """A pairing code could not be built."""


def expires_at(now=None, lifetime_seconds: int = DEFAULT_LIFETIME_SECONDS) -> int:
    """The moment the code stops being usable, in whole seconds."""
    moment = time.time() if now is None else now
    return int(moment) + int(lifetime_seconds)


def pairing_payload(bridge_url: str, key_id: str, secret: str,
                    expires: int) -> str:
    """The text of the pairing code."""
    if not isinstance(bridge_url, str) or not bridge_url.strip():
        raise PairingCodeError('A bridge address for the phone is required.')
    if not bridge_url.strip().lower().startswith('https://'):
        raise PairingCodeError('The bridge address for the phone must use HTTPS.')
    if not isinstance(key_id, str) or not key_id.strip():
        raise PairingCodeError('A device key id is required.')
    if not isinstance(secret, str) or len(secret) < MINIMUM_SECRET_LENGTH:
        raise PairingCodeError('The pairing secret is too short to use.')
    if not isinstance(expires, int) or expires <= 0:
        raise PairingCodeError('The pairing code needs an expiry.')
    return '\n'.join([
        PAIRING_FORMAT,
        'bridge=' + bridge_url.strip(),
        'key=' + key_id.strip(),
        'secret=' + secret,
        'expires=' + str(expires),
    ])


def pairing_svg(payload: str) -> str:
    """The pairing code as an SVG picture.

    The picture is drawn by the `qrcode` package. It is a pure Python package
    and the SVG output needs no image library, so nothing heavy is added to
    the installation.
    """
    import qrcode
    from qrcode.image.svg import SvgImage

    code = qrcode.QRCode(border=2, box_size=8)
    code.add_data(payload)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgImage)
    picture = image.to_string()
    if isinstance(picture, bytes):
        picture = picture.decode('utf-8')
    return picture


def pairing_matrix(payload: str) -> list[list[bool]]:
    """The pairing code as a matrix of dark and light cells.

    The tests use it to draw the code into a picture and read it back with
    the decoder that the phone uses.
    """
    import qrcode

    code = qrcode.QRCode(border=2, box_size=1)
    code.add_data(payload)
    code.make(fit=True)
    return [[bool(cell) for cell in row] for row in code.get_matrix()]
