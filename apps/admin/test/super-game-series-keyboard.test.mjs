import assert from 'node:assert/strict';
import test from 'node:test';

import {
  SUPER_GAME_SERIES_SHORTCUT_SYMBOL_LIMIT,
  isSuperGameSeriesShortcutBlocked,
  resolveSuperGameSeriesKeyboardCommand,
  superGameSeriesShortcutLabel,
} from '../src/features/super-games/super-game-series-keyboard.ts';

const symbols = Array.from({ length: 10 }, (_, index) => ({
  id: `symbol-${index + 1}`,
}));

function key(value, modifiers = {}) {
  return {
    altKey: false,
    ctrlKey: false,
    key: value,
    metaKey: false,
    shiftKey: false,
    ...modifiers,
  };
}

test('digits select symbols of the shown list and 0 the tenth', () => {
  assert.deepEqual(resolveSuperGameSeriesKeyboardCommand(key('1'), symbols), {
    kind: 'select_symbol',
    symbolId: 'symbol-1',
  });
  assert.deepEqual(resolveSuperGameSeriesKeyboardCommand(key('9'), symbols), {
    kind: 'select_symbol',
    symbolId: 'symbol-9',
  });
  assert.deepEqual(resolveSuperGameSeriesKeyboardCommand(key('0'), symbols), {
    kind: 'select_symbol',
    symbolId: 'symbol-10',
  });
  assert.equal(SUPER_GAME_SERIES_SHORTCUT_SYMBOL_LIMIT, 10);
  assert.equal(superGameSeriesShortcutLabel(9), '0');
  assert.equal(superGameSeriesShortcutLabel(0), '1');
  assert.equal(superGameSeriesShortcutLabel(10), null);
});

test('digits without a matching symbol are ignored', () => {
  assert.equal(
    resolveSuperGameSeriesKeyboardCommand(key('0'), symbols.slice(0, 9)),
    null,
  );
  assert.equal(
    resolveSuperGameSeriesKeyboardCommand(key('4'), symbols.slice(0, 3)),
    null,
  );
  assert.equal(resolveSuperGameSeriesKeyboardCommand(key('a'), symbols), null);
  assert.equal(resolveSuperGameSeriesKeyboardCommand(key('10'), symbols), null);
});

test('Enter saves, Escape cancels and arrows move the carousel', () => {
  assert.deepEqual(resolveSuperGameSeriesKeyboardCommand(key('Enter'), []), {
    kind: 'save',
  });
  assert.deepEqual(resolveSuperGameSeriesKeyboardCommand(key('Escape'), []), {
    kind: 'cancel',
  });
  assert.deepEqual(
    resolveSuperGameSeriesKeyboardCommand(key('ArrowLeft'), []),
    { kind: 'previous' },
  );
  assert.deepEqual(
    resolveSuperGameSeriesKeyboardCommand(key('ArrowRight'), []),
    { kind: 'next' },
  );
});

test('modified keys keep browser shortcuts', () => {
  for (const modifier of ['altKey', 'ctrlKey', 'metaKey', 'shiftKey']) {
    for (const value of [
      '1',
      '0',
      'Enter',
      'Escape',
      'ArrowLeft',
      'ArrowRight',
    ]) {
      assert.equal(
        resolveSuperGameSeriesKeyboardCommand(
          key(value, { [modifier]: true }),
          symbols,
        ),
        null,
        `${modifier} + ${value}`,
      );
    }
  }
});

test('events without shiftKey are still resolved', () => {
  assert.deepEqual(
    resolveSuperGameSeriesKeyboardCommand(
      { altKey: false, ctrlKey: false, key: 'Enter', metaKey: false },
      [],
    ),
    { kind: 'save' },
  );
});

test('shortcuts are blocked in text fields and selects, and Enter on buttons', () => {
  class FakeElement {
    constructor(tagName, extra = {}) {
      this.tagName = tagName;
      this.isContentEditable = false;
      Object.assign(this, extra);
    }
  }
  const original = globalThis.HTMLElement;
  globalThis.HTMLElement = FakeElement;
  try {
    assert.equal(
      isSuperGameSeriesShortcutBlocked(
        new FakeElement('INPUT', { type: 'text' }),
        '1',
      ),
      true,
    );
    assert.equal(
      isSuperGameSeriesShortcutBlocked(new FakeElement('TEXTAREA'), '1'),
      true,
    );
    assert.equal(
      isSuperGameSeriesShortcutBlocked(new FakeElement('SELECT'), 'ArrowLeft'),
      true,
    );
    assert.equal(
      isSuperGameSeriesShortcutBlocked(
        new FakeElement('DIV', { isContentEditable: true }),
        '1',
      ),
      true,
    );
    // A focused button keeps its own Enter but does not block digits/arrows.
    assert.equal(
      isSuperGameSeriesShortcutBlocked(new FakeElement('BUTTON'), 'Enter'),
      true,
    );
    assert.equal(
      isSuperGameSeriesShortcutBlocked(new FakeElement('BUTTON'), 'ArrowRight'),
      false,
    );
    assert.equal(
      isSuperGameSeriesShortcutBlocked(new FakeElement('A'), 'Enter'),
      true,
    );
    assert.equal(
      isSuperGameSeriesShortcutBlocked(new FakeElement('DIV'), 'Enter'),
      false,
    );
    assert.equal(isSuperGameSeriesShortcutBlocked(null, 'Enter'), false);
  } finally {
    if (original === undefined) delete globalThis.HTMLElement;
    else globalThis.HTMLElement = original;
  }
});
