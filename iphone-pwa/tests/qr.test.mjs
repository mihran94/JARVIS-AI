// Reading a pairing code from a picture.
import test from 'node:test';
import assert from 'node:assert/strict';

import { decodeQrFromFile, decodeQrFromImageData } from '../js/qr.js';

/** A decoder that always answers with the same text. */
function fakeDecoder(text) {
  return (data, width, height) => (text ? { data: text } : null);
}

test('a code in the picture is read', () => {
  const imageData = { data: new Uint8ClampedArray(4), width: 2, height: 2 };
  const text = decodeQrFromImageData(imageData, fakeDecoder('JARVIS-BRIDGE-v1'));
  assert.equal(text, 'JARVIS-BRIDGE-v1');
});

test('a picture without a code gives nothing', () => {
  const imageData = { data: new Uint8ClampedArray(4), width: 2, height: 2 };
  assert.equal(decodeQrFromImageData(imageData, fakeDecoder('')), '');
});

test('an empty picture gives nothing', () => {
  assert.equal(decodeQrFromImageData({ data: [], width: 0, height: 0 }, fakeDecoder('x')), '');
  assert.equal(decodeQrFromImageData(null, fakeDecoder('x')), '');
});

test('a browser without the decoder is reported', () => {
  assert.throws(() => decodeQrFromImageData({ data: [], width: 1, height: 1 }, null),
    /decoder is not available/);
});

test('a picture file is turned into a picture and read', async () => {
  const drawn = [];
  const fakeBitmap = { width: 4, height: 3 };
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ({
      drawImage(bitmap) { drawn.push(bitmap); },
      getImageData: (x, y, width, height) => ({ data: new Uint8ClampedArray(width * height * 4), width, height }),
    }),
  };
  const text = await decodeQrFromFile({ name: 'code.png' }, {
    decoder: fakeDecoder('JARVIS-BRIDGE-v1'),
    createImageBitmapImpl: async () => fakeBitmap,
    canvasFactory: () => canvas,
  });
  assert.equal(text, 'JARVIS-BRIDGE-v1');
  assert.equal(canvas.width, 4);
  assert.equal(canvas.height, 3);
  assert.equal(drawn.length, 1);
});

test('a browser that cannot read a picture is reported', async () => {
  await assert.rejects(() => decodeQrFromFile({ name: 'code.png' }, {
    decoder: fakeDecoder('x'),
    createImageBitmapImpl: undefined,
  }), /cannot read the picture/);
});
