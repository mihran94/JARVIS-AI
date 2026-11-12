// Read a QR code that was drawn elsewhere.
//
// The desktop draws the pairing code with a Python QR encoder. This helper
// takes the matrix of that code and reads it back with the decoder the
// iPhone uses, so the test can prove that the two agree.
//
// The matrix is read from the standard input as a JSON array of rows, where
// a true value is a dark cell.
//
//     echo '[[true,false],[false,true]]' | node tools/decode-matrix.mjs

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

/**
 * The vendored decoder is a universal build, so it is evaluated here with a
 * small module wrapper. The package is an ES module, so it cannot simply be
 * required.
 */
function loadDecoder() {
  const source = readFileSync(join(here, '..', 'vendor', 'jsQR.js'), 'utf8');
  const module = { exports: {} };
  const factory = new Function('module', 'exports', source);
  factory(module, module.exports);
  return module.exports;
}

/** The pixels of the matrix, drawn with a quiet border. */
function toImageData(matrix, scale = 4, border = 4) {
  const size = matrix.length;
  const width = (size + border * 2) * scale;
  const height = width;
  const pixels = new Uint8ClampedArray(width * width * 4).fill(255);
  for (let row = 0; row < size; row += 1) {
    for (let column = 0; column < size; column += 1) {
      if (!matrix[row][column]) {
        continue;
      }
      for (let y = 0; y < scale; y += 1) {
        for (let x = 0; x < scale; x += 1) {
          const pixelX = (column + border) * scale + x;
          const pixelY = (row + border) * scale + y;
          const offset = (pixelY * width + pixelX) * 4;
          pixels[offset] = 0;
          pixels[offset + 1] = 0;
          pixels[offset + 2] = 0;
          pixels[offset + 3] = 255;
        }
      }
    }
  }
  return { data: pixels, width, height };
}

async function main() {
  const input = await new Promise((resolve) => {
    let text = '';
    process.stdin.on('data', (chunk) => { text += chunk; });
    process.stdin.on('end', () => resolve(text));
  });
  const matrix = JSON.parse(input);
  const decoder = loadDecoder();
  const imageData = toImageData(matrix);
  const result = decoder(imageData.data, imageData.width, imageData.height, {
    inversionAttempts: 'attemptBoth',
  });
  process.stdout.write(result && result.data ? result.data : '');
}

main().catch((error) => {
  process.stderr.write(String(error && error.stack ? error.stack : error));
  process.exit(1);
});
