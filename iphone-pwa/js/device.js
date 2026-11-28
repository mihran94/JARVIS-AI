// Remember a non-exportable signing key, never the QR's raw pairing secret.
import { validSigningKey } from './bridge.js';

export async function deviceRecord(client, origin) {
  if (new URL(client.baseUrl).origin !== origin || !origin.startsWith('https://')) {
    throw new Error('Remember this browser is available only on the PC’s own HTTPS page.');
  }
  const signingKey = client.signingKey || await crypto.subtle.importKey('raw',
    new TextEncoder().encode(client.secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  if (!validSigningKey(signingKey)) throw new Error('Invalid device signing key.');
  return { baseUrl: origin, keyId: client.keyId, signingKey };
}

export function deviceStorage(indexedDb = globalThis.indexedDB) {
  async function operation(mode, value) {
    if (!indexedDb) return null;
    const db = await new Promise((resolve, reject) => {
      const request = indexedDb.open('jarvis-paired-browser', 1);
      request.onupgradeneeded = () => request.result.createObjectStore('device');
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(new Error('Browser could not open device storage.'));
    });
    try {
      return await new Promise((resolve, reject) => {
        const transaction = db.transaction('device', mode === 'read' ? 'readonly' : 'readwrite');
        const store = transaction.objectStore('device');
        const request = mode === 'read' ? store.get('paired') : mode === 'write' ? store.put(value, 'paired') : store.delete('paired');
        transaction.oncomplete = () => resolve(request.result || null);
        transaction.onerror = transaction.onabort = () => reject(new Error('Browser could not save the device connection.'));
      });
    } finally { db.close(); }
  }
  return { read: () => operation('read'), write: (value) => operation('write', value), clear: () => operation('clear') };
}
