import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  BOARD_SEARCH_UNKNOWN_SHORTCUT,
  resolveBoardSearchKeyboardCommand,
} from '../src/features/board-search/board-search-keyboard.ts';
import {
  digitShortcutIndex,
  digitShortcutLabel,
  isTextEntryKeyboardTarget,
} from '../src/lib/keyboard-shortcuts.ts';

const symbols = Array.from({ length: 10 }, (_, index) => ({
  code: `S${index + 1}`,
}));

function key(value, modifiers = {}) {
  return {
    altKey: false,
    ctrlKey: false,
    key: value,
    metaKey: false,
    ...modifiers,
  };
}

test('digits place active symbols in catalog order', () => {
  assert.deepEqual(resolveBoardSearchKeyboardCommand(key('1'), symbols), {
    kind: 'place_symbol',
    symbolCode: 'S1',
  });
  assert.deepEqual(resolveBoardSearchKeyboardCommand(key('9'), symbols), {
    kind: 'place_symbol',
    symbolCode: 'S9',
  });
  assert.equal(
    resolveBoardSearchKeyboardCommand(key('5'), symbols.slice(0, 4)),
    null,
  );
});

test('0 and ? place the unknown marker', () => {
  assert.equal(BOARD_SEARCH_UNKNOWN_SHORTCUT, '0');
  for (const value of ['0', '?']) {
    assert.deepEqual(resolveBoardSearchKeyboardCommand(key(value), symbols), {
      kind: 'place_unknown',
    });
  }
});

test('Backspace undoes, Enter searches, other keys are ignored', () => {
  assert.deepEqual(resolveBoardSearchKeyboardCommand(key('Backspace'), []), {
    kind: 'undo',
  });
  assert.deepEqual(resolveBoardSearchKeyboardCommand(key('Enter'), []), {
    kind: 'search',
  });
  assert.equal(resolveBoardSearchKeyboardCommand(key('a'), symbols), null);
  assert.equal(resolveBoardSearchKeyboardCommand(key('Escape'), symbols), null);
});

test('modified keys keep browser shortcuts', () => {
  for (const modifier of ['altKey', 'ctrlKey', 'metaKey']) {
    for (const value of ['1', '0', 'Enter', 'Backspace']) {
      assert.equal(
        resolveBoardSearchKeyboardCommand(
          key(value, { [modifier]: true }),
          symbols,
        ),
        null,
      );
    }
  }
});

test('shared digit helpers', () => {
  assert.equal(digitShortcutIndex('1'), 0);
  assert.equal(digitShortcutIndex('9'), 8);
  assert.equal(digitShortcutIndex('0'), null);
  assert.equal(digitShortcutIndex('12'), null);
  assert.equal(digitShortcutLabel(0), '1');
  assert.equal(digitShortcutLabel(9), null);
  assert.equal(isTextEntryKeyboardTarget(null), false);
});

test('workspace wires the palette shortcuts', async () => {
  const source = await readFile(
    new URL(
      '../src/features/board-search/board-search-workspace.tsx',
      import.meta.url,
    ),
    'utf8',
  );
  assert.match(source, /window\.addEventListener\('keydown'/);
  assert.match(source, /isTextEntryKeyboardTarget\(event\.target\)/);
  assert.match(
    source,
    /resolveBoardSearchKeyboardCommand\(event, activeSymbols\)/,
  );
  assert.match(source, /composerRef\.current\?\.contains\(target\)/);
  assert.match(source, /className="boardSearchSymbolShortcut"/);
  assert.match(source, /aria-keyshortcuts=/);
});
