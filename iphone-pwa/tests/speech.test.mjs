// Voice in Tamil and English, with the limits of iOS Safari respected.
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  LANGUAGES, chooseLanguage, defaultLanguage, isTamil, recognitionSupported,
  speak, speakLanguage, startListening, synthesisSupported,
} from '../js/speech.js';

/** A stand in for the browser recogniser. */
class FakeRecognition {
  constructor() {
    FakeRecognition.lastInstance = this;
    this.lang = '';
    this.continuous = false;
    this.interimResults = false;
    this.onresult = null;
    this.onerror = null;
    this.onend = null;
    this.started = false;
  }

  start() {
    this.started = true;
  }

  stop() {
    this.started = false;
  }
}

test('Tamil is recognised by its characters', () => {
  assert.equal(isTamil('வணக்கம் ஜார்விஸ்'), true);
  assert.equal(isTamil('hello'), false);
  assert.equal(isTamil('வணக்கம் hello'), true);
});

test('Tamil is spoken and heard in Tamil', () => {
  assert.equal(chooseLanguage('வணக்கம்'), 'ta-IN');
  assert.equal(speakLanguage('வணக்கம்'), 'ta-IN');
});

test('English keeps the language that is already in use', () => {
  assert.equal(chooseLanguage('hello', { current: 'en-US' }), 'en-US');
  assert.equal(chooseLanguage('hello', { current: 'ta-IN' }), 'ta-IN');
});

test('the two languages are the agreed ones', () => {
  assert.deepEqual(LANGUAGES.map((language) => language.code), ['ta-IN', 'en-US']);
});

test('the default language follows the phone', () => {
  const original = globalThis.navigator;
  try {
    Object.defineProperty(globalThis, 'navigator', { value: { language: 'ta-IN' }, configurable: true });
    assert.equal(defaultLanguage(), 'ta-IN');
    Object.defineProperty(globalThis, 'navigator', { value: { language: 'en-GB' }, configurable: true });
    assert.equal(defaultLanguage(), 'en-US');
  } finally {
    Object.defineProperty(globalThis, 'navigator', { value: original, configurable: true });
  }
});

test('a browser without speech is reported', () => {
  assert.equal(recognitionSupported(undefined), false);
  assert.equal(recognitionSupported(FakeRecognition), true);
  assert.equal(synthesisSupported(undefined), false);
  assert.equal(synthesisSupported({ speak() {} }), true);
});

test('listening gives the spoken text', () => {
  const seen = [];
  const handle = startListening({
    constructor: FakeRecognition,
    lang: 'ta-IN',
    onResult: (text, lang) => seen.push([text, lang]),
  });
  const recogniser = FakeRecognition.lastInstance;
  assert.equal(recogniser.started, true);
  assert.equal(recogniser.lang, 'ta-IN');
  assert.equal(recogniser.continuous, false);
  recogniser.onresult({ results: [[{ transcript: '  வணக்கம்  ' }]] });
  assert.deepEqual(seen, [['வணக்கம்', 'ta-IN']]);
  handle.stop();
  assert.equal(recogniser.started, false);
});

test('a recognition error is reported', () => {
  const errors = [];
  startListening({ constructor: FakeRecognition, onError: (error) => errors.push(error) });
  FakeRecognition.lastInstance.onerror({ error: 'not-allowed' });
  assert.deepEqual(errors, ['not-allowed']);
});

test('a browser without recognition refuses to listen', () => {
  assert.throws(() => startListening({ constructor: undefined }), /cannot recognise speech/);
});

test('speaking needs a browser that can speak', () => {
  assert.equal(speak('hello', { synthesis: undefined }), false);
  assert.equal(speak('', { synthesis: { speak() {} } }), false);
});

test('speaking uses the language of the line', () => {
  const spoken = [];
  const fakeSynthesis = {
    cancel() {},
    speak(utterance) {
      spoken.push({ text: utterance.text, lang: utterance.lang });
    },
  };
  const originalUtterance = globalThis.SpeechSynthesisUtterance;
  globalThis.SpeechSynthesisUtterance = class {
    constructor(text) {
      this.text = text;
    }
  };
  try {
    assert.equal(speak('வணக்கம்', { synthesis: fakeSynthesis, lang: 'ta-IN' }), true);
    assert.deepEqual(spoken, [{ text: 'வணக்கம்', lang: 'ta-IN' }]);
  } finally {
    globalThis.SpeechSynthesisUtterance = originalUtterance;
  }
});
