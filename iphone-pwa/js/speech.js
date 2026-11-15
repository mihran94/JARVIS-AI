// Voice for the phone, in Tamil, English and French.
//
// iOS Safari supports the Web Speech API, but only partly: speech
// recognition exists, and it has to be started from a user gesture. There is
// no way to run it in the background, and there is no way to make the phone
// answer while the app is closed. This module therefore never claims more
// than the browser can do.
//
// Everything the browser provides is injected, so the rules can be tested
// without a device.

/** The languages this app speaks. */
export const LANGUAGES = [
  { code: 'ta-IN', name: 'தமிழ்', english: 'Tamil' },
  { code: 'en-US', name: 'English', english: 'English' },
  { code: 'fr-FR', name: 'Français', english: 'French' },
];

/** The characters that mark a line as Tamil. */
const TAMIL_PATTERN = /[\u0B80-\u0BFF]/;

// Common French phrases help select a voice when the reply differs from
// the microphone language. The user's selection remains the fallback.
const FRENCH_PATTERN = /(?:^|[^\p{L}])(?:bonjour|bonsoir|salut|merci|pourquoi|comment allez-vous|je suis|ça va|s'il vous plaît)(?=$|[^\p{L}])/iu;

/** Whether a line is written in Tamil. */
export function isTamil(text) {
  return typeof text === 'string' && TAMIL_PATTERN.test(text);
}

/** Whether a line is written in French. */
export function isFrench(text) {
  if (typeof text !== 'string' || !text) {
    return false;
  }
  return FRENCH_PATTERN.test(text.normalize('NFC'));
}

/**
 * The language to use for a line.
 *
 * Tamil wins when the text has Tamil characters, and French comes next when
 * it has the accented letters. Otherwise the language that the browser is
 * already using is kept, so a person who speaks English does not have to
 * change a setting.
 */
export function chooseLanguage(text, { current = 'en-US' } = {}) {
  if (isTamil(text)) {
    return 'ta-IN';
  }
  if (isFrench(text)) {
    return 'fr-FR';
  }
  return current;
}

/** The language the page should listen in by default. */
export function defaultLanguage() {
  const language = (globalThis.navigator && globalThis.navigator.language) || 'en-US';
  const lower = language.toLowerCase();
  if (lower.startsWith('ta')) {
    return 'ta-IN';
  }
  if (lower.startsWith('fr')) {
    return 'fr-FR';
  }
  return 'en-US';
}

/** Whether this browser can recognise speech. */
export function recognitionSupported(constructor = globalThis.SpeechRecognition ||
  globalThis.webkitSpeechRecognition) {
  return typeof constructor === 'function';
}

/** Whether this browser can speak. */
export function synthesisSupported(synthesis = globalThis.speechSynthesis) {
  return Boolean(synthesis) && typeof synthesis.speak === 'function';
}

/**
 * Start listening.
 *
 * The caller has to start this from a user gesture, because Safari refuses
 * otherwise. The recogniser is stopped by the page when the person presses
 * the button again.
 */
export function startListening({
  constructor = globalThis.SpeechRecognition || globalThis.webkitSpeechRecognition,
  lang = defaultLanguage(),
  onResult = () => {},
  onError = () => {},
  onEnd = () => {},
} = {}) {
  if (!recognitionSupported(constructor)) {
    throw new Error('This browser cannot recognise speech.');
  }
  const recogniser = new constructor();
  recogniser.lang = lang;
  recogniser.continuous = false;
  recogniser.interimResults = false;
  let finished = false;
  recogniser.onresult = (event) => {
    const results = event.results;
    const last = results[results.length - 1];
    if (!last) {
      return;
    }
    const text = last[0] ? last[0].transcript : '';
    onResult(text.trim(), lang);
  };
  recogniser.onerror = (event) => {
    finished = true;
    onError(event && event.error ? event.error : 'unknown', lang);
  };
  recogniser.onend = () => {
    if (!finished) {
      finished = true;
      onEnd(lang);
    }
  };
  recogniser.start();
  return {
    stop() {
      try {
        recogniser.stop();
      } catch (error) {
        /* the recogniser was already stopped */
      }
    },
    get listening() {
      return !finished;
    },
  };
}

/**
 * Say a line out loud.
 *
 * The page has to be in the foreground and the language has to be one of the
 * ones that are installed on the phone, otherwise nothing is said.
 */
export function speak(text, {
  synthesis = globalThis.speechSynthesis,
  lang = 'en-US',
  rate = 1,
} = {}) {
  if (!synthesisSupported(synthesis)) {
    return false;
  }
  if (!text) {
    return false;
  }
  synthesis.cancel();
  const utterance = new globalThis.SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.rate = rate;
  synthesis.speak(utterance);
  return true;
}

/** The language to speak a line in. */
export function speakLanguage(text, { current = 'en-US' } = {}) {
  return chooseLanguage(text, { current });
}
