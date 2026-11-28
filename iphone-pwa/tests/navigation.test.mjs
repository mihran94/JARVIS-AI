import test from 'node:test';
import assert from 'node:assert/strict';
import { createNavigation } from '../js/navigation.js';

test('section changes preserve page state and notify the display to stop', () => {
  const panels = ['pairing', 'chatPanel', 'displayPanel'].map((id) => ({ id, hidden: false, draft: 'keep me' }));
  const links = panels.map((panel) => ({
    attributes: { href: `#${panel.id}` },
    getAttribute(name) { return this.attributes[name]; },
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; },
    addEventListener(event, callback) { this.click = callback; },
  }));
  const changed = [];
  const navigation = createNavigation({
    querySelectorAll: () => links,
    getElementById: (id) => panels.find((panel) => panel.id === id),
  }, (id) => changed.push(id));
  let prevented = false;
  links[2].click({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.deepEqual(panels.map((panel) => panel.hidden), [true, true, false]);
  navigation.show('chatPanel');
  assert.equal(links[1].attributes['aria-current'], 'page');
  assert.equal(links[2].attributes['aria-current'], undefined);
  assert.equal(panels[1].draft, 'keep me');
  assert.deepEqual(changed, ['pairing', 'displayPanel', 'chatPanel']);
  assert.equal(navigation.show('pair=secret'), false);
  assert.equal(changed.length, 3);
});
