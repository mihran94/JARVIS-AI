import test from 'node:test';
import assert from 'node:assert/strict';
import { DesktopViewer } from '../js/display.js';

test('stopping during a request discards the frame and schedules no more captures', async () => {
  let finish;
  const frames = [], scheduled = [];
  const viewer = new DesktopViewer({
    fetchFrame: () => new Promise((resolve) => { finish = resolve; }),
    showFrame: (frame) => frames.push(frame), status: () => {},
    schedule: (callback) => scheduled.push(callback), cancel: () => {},
  });
  viewer.start();
  viewer.stop();
  finish({ image: 'data:image/jpeg;base64,YQ==' });
  await new Promise(setImmediate);
  assert.deepEqual(frames, []);
  assert.deepEqual(scheduled, []);
});

test('a capture failure stops polling and permits retry', async () => {
  const statuses = [];
  const viewer = new DesktopViewer({
    fetchFrame: async () => { throw new Error('Connect your PC first.'); },
    showFrame: () => assert.fail('no frame expected'),
    status: (message) => statuses.push(message),
    schedule: () => assert.fail('no retry loop expected'), cancel: () => {},
  });
  viewer.start();
  await new Promise(setImmediate);
  assert.equal(viewer.active, false);
  assert.equal(statuses.at(-1), 'Connect your PC first.');
});

test('successful capture schedules the next frame only after completion', async () => {
  const frames = [], scheduled = [];
  const viewer = new DesktopViewer({
    fetchFrame: async () => ({ image: 'data:image/jpeg;base64,YQ==' }),
    showFrame: (frame) => frames.push(frame), status: () => {},
    schedule: (callback, delay) => { scheduled.push([callback, delay]); return 1; }, cancel: () => {},
  });
  viewer.start(); viewer.start();
  await new Promise(setImmediate);
  assert.equal(frames.length, 1);
  assert.equal(scheduled.length, 1);
  assert.equal(scheduled[0][1], 1000);
  viewer.stop();
});
