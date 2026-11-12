# Vendored third party code

## jsQR 1.4.0

| | |
| --- | --- |
| Source | https://github.com/cozmo/jsQR |
| Version | 1.4.0 |
| Licence | Apache License 2.0, see `jsQR.LICENSE` |
| File | `jsQR.js` (the published universal build) |

jsQR decodes a QR code from a still image. It is used to read the pairing
code that the Windows desktop displays, so a phone can be paired without
typing a long secret by hand.

Why it is vendored: the iPhone page must work from a private HTTPS origin
without a package registry and without a network call, and the decoder has to
be available offline.

Why the camera route works on iOS: Safari does not implement the
`BarcodeDetector` API, so the page reads a photo through a file input with
`capture` and decodes the image locally. The photo is never uploaded.
