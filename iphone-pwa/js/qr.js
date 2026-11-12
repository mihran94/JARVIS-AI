// Reading a QR code from a photo.
//
// iOS Safari does not implement the `BarcodeDetector` API, so the page reads
// a photo through a file input with `capture` and decodes the picture
// locally with the vendored decoder. The photo never leaves the phone.
//
// The decoder is injected, so the rules can be tested without a camera.

/** The decoder that is used when the page does not pass one. */
export function defaultDecoder() {
  return globalThis.jsQR || null;
}

/**
 * Read a QR code from image data.
 *
 * Returns the text of the code, or an empty string when the picture holds no
 * code that can be read.
 */
export function decodeQrFromImageData(imageData, decoder = defaultDecoder()) {
  if (!decoder) {
    throw new Error('The QR decoder is not available.');
  }
  if (!imageData || !imageData.data || !imageData.width || !imageData.height) {
    return '';
  }
  const result = decoder(imageData.data, imageData.width, imageData.height, {
    inversionAttempts: 'attemptBoth',
  });
  return result && result.data ? result.data : '';
}

/**
 * Read a QR code from a picture file.
 *
 * The picture is turned into image data with the browser and decoded. The
 * browser parts are injected so the logic can be tested without a device.
 */
export async function decodeQrFromFile(file, {
  decoder = defaultDecoder(),
  createImageBitmapImpl = globalThis.createImageBitmap,
  canvasFactory = null,
} = {}) {
  if (!file) {
    return '';
  }
  if (!createImageBitmapImpl) {
    throw new Error('This browser cannot read the picture.');
  }
  const bitmap = await createImageBitmapImpl(file);
  const width = bitmap.width;
  const height = bitmap.height;
  if (!width || !height) {
    return '';
  }
  const canvas = canvasFactory ? canvasFactory() : globalThis.document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) {
    throw new Error('This browser cannot read the picture.');
  }
  context.drawImage(bitmap, 0, 0);
  const imageData = context.getImageData(0, 0, width, height);
  return decodeQrFromImageData(imageData, decoder);
}
