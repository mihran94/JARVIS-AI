// The chat transcript of the phone.
//
// The transcript is kept apart from the page so it can be tested without a
// browser, and so the same list can be shown, copied or cleared.
//
// The phone never holds a provider key. It sends a message to the PC and
// shows the answer the PC gives back.

/** The roles a message can have. */
export const ROLES = ['person', 'jarvis', 'system'];

/** One line of the transcript. */
export class Message {
  constructor(role, text, at = 0) {
    if (!ROLES.includes(role)) {
      throw new Error(`Unknown message role: ${role}`);
    }
    this.role = role;
    this.text = String(text ?? '');
    this.at = at;
  }

  toJSON() {
    return { role: this.role, text: this.text, at: this.at };
  }
}

/** The ordered list of messages. */
export class ChatTranscript {
  constructor({ now = Date.now, limit = 200 } = {}) {
    this.now = now;
    this.limit = limit;
    this.messages = [];
  }

  /** Add a line and return it. */
  add(role, text) {
    const message = new Message(role, text, this.now());
    this.messages.push(message);
    while (this.messages.length > this.limit) {
      this.messages.shift();
    }
    return message;
  }

  /** The last message with this role. */
  last(role) {
    for (let index = this.messages.length - 1; index >= 0; index -= 1) {
      if (this.messages[index].role === role) {
        return this.messages[index];
      }
    }
    return null;
  }

  /** The whole transcript as text. */
  toText() {
    return this.messages.map((message) => `${message.role}: ${message.text}`).join('\n');
  }

  /** Forget everything. */
  clear() {
    this.messages = [];
  }
}

/**
 * Draw the transcript into an element.
 *
 * The document is injected so this can be tested without a browser. Each
 * line is a separate element, and the element is asked to scroll to the end
 * when the transcript changes.
 */
export function renderTranscript(transcript, container, { documentRef = globalThis.document } = {}) {
  if (!container) {
    throw new Error('A container is required.');
  }
  container.textContent = '';
  for (const message of transcript.messages) {
    const line = documentRef.createElement('p');
    line.className = `line line-${message.role}`;
    line.setAttribute('data-role', message.role);
    line.textContent = message.text;
    container.appendChild(line);
  }
  if (typeof container.scrollTo === 'function') {
    container.scrollTo({ top: container.scrollHeight });
  }
  return container.childElementCount ?? container.children.length;
}
