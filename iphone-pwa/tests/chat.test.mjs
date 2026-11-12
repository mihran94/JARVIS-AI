// The chat transcript of the phone.
import test from 'node:test';
import assert from 'node:assert/strict';

import { ChatTranscript, Message, renderTranscript } from '../js/chat.js';

/** The smallest element that behaves enough like a DOM node for the tests. */
function fakeDocument() {
  const create = (tag) => {
    const node = {
      tagName: tag.toUpperCase(),
      children: [],
      attributes: {},
      className: '',
      textContent: '',
      get childElementCount() {
        return node.children.length;
      },
      append(child) {
        node.children.push(child);
      },
      setAttribute(name, value) {
        node.attributes[name] = value;
      },
    };
    return node;
  };
  return { createElement: create };
}

function fakeContainer() {
  const container = {
    children: [],
    scrollHeight: 100,
    scrollTo() {},
    append(child) {
      container.children.push(child);
    },
    appendChild(child) {
      container.children.push(child);
      return child;
    },
    get childElementCount() {
      return container.children.length;
    },
  };
  // Setting the text of an element removes its children, as it does in a
  // browser.
  let text = '';
  Object.defineProperty(container, 'textContent', {
    get() {
      return text;
    },
    set(value) {
      text = value;
      container.children = [];
    },
  });
  return container;
}

test('a message keeps its role and its text', () => {
  const message = new Message('person', 'hello', 5);
  assert.equal(message.role, 'person');
  assert.equal(message.text, 'hello');
  assert.deepEqual(message.toJSON(), { role: 'person', text: 'hello', at: 5 });
});

test('an unknown role is refused', () => {
  assert.throws(() => new Message('robot', 'hi'), /Unknown message role/);
});

test('the transcript keeps the order', () => {
  const transcript = new ChatTranscript({ now: () => 1 });
  transcript.add('person', 'one');
  transcript.add('jarvis', 'two');
  assert.deepEqual(transcript.messages.map((message) => message.text), ['one', 'two']);
  assert.equal(transcript.last('jarvis').text, 'two');
  assert.equal(transcript.last('person').text, 'one');
  assert.equal(transcript.last('system'), null);
});

test('the transcript is bounded', () => {
  const transcript = new ChatTranscript({ limit: 3 });
  for (let index = 0; index < 10; index += 1) {
    transcript.add('person', `line ${index}`);
  }
  assert.equal(transcript.messages.length, 3);
  assert.equal(transcript.messages[0].text, 'line 7');
});

test('the transcript can be read as text', () => {
  const transcript = new ChatTranscript();
  transcript.add('person', 'one');
  transcript.add('jarvis', 'two');
  assert.equal(transcript.toText(), 'person: one\njarvis: two');
});

test('the transcript can be cleared', () => {
  const transcript = new ChatTranscript();
  transcript.add('person', 'one');
  transcript.clear();
  assert.equal(transcript.messages.length, 0);
});

test('drawing the transcript puts one element per message', () => {
  const transcript = new ChatTranscript();
  transcript.add('person', 'one');
  transcript.add('jarvis', 'two');
  const container = fakeContainer();
  const count = renderTranscript(transcript, container, { documentRef: fakeDocument() });
  assert.equal(count, 2);
  assert.equal(container.children[0].attributes['data-role'], 'person');
  assert.equal(container.children[1].textContent, 'two');
});

test('drawing again replaces the old lines', () => {
  const transcript = new ChatTranscript();
  transcript.add('person', 'one');
  const container = fakeContainer();
  renderTranscript(transcript, container, { documentRef: fakeDocument() });
  transcript.add('jarvis', 'two');
  renderTranscript(transcript, container, { documentRef: fakeDocument() });
  assert.equal(container.childElementCount, 2);
});

test('drawing needs a container', () => {
  assert.throws(() => renderTranscript(new ChatTranscript(), null), /container is required/);
});
