import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  SYMBOL_REVIEW_SHORTCUT_SYMBOL_LIMIT,
  isSymbolReviewTextEntryTarget,
  resolveSymbolReviewKeyboardCommand,
  symbolReviewShortcutLabel,
} from '../src/features/symbol-reviews/symbol-review-keyboard.ts';

const symbols = Array.from({ length: 11 }, (_, index) => ({
  id: `symbol-${index + 1}`,
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

test('digits select active symbols in catalog order', () => {
  assert.deepEqual(resolveSymbolReviewKeyboardCommand(key('1'), symbols), {
    kind: 'select_target',
    symbolId: 'symbol-1',
  });
  assert.deepEqual(resolveSymbolReviewKeyboardCommand(key('8'), symbols), {
    kind: 'select_target',
    symbolId: 'symbol-8',
  });
  assert.deepEqual(resolveSymbolReviewKeyboardCommand(key('9'), symbols), {
    kind: 'select_target',
    symbolId: 'symbol-9',
  });
});

test('digits without a matching symbol and 0 are ignored', () => {
  assert.equal(
    resolveSymbolReviewKeyboardCommand(key('4'), symbols.slice(0, 3)),
    null,
  );
  assert.equal(resolveSymbolReviewKeyboardCommand(key('0'), symbols), null);
  assert.equal(resolveSymbolReviewKeyboardCommand(key('10'), symbols), null);
  assert.equal(resolveSymbolReviewKeyboardCommand(key('a'), symbols), null);
});

test('Enter applies and Escape cancels', () => {
  assert.deepEqual(resolveSymbolReviewKeyboardCommand(key('Enter'), []), {
    kind: 'apply',
  });
  assert.deepEqual(resolveSymbolReviewKeyboardCommand(key('Escape'), []), {
    kind: 'cancel',
  });
});

test('modified keys keep browser shortcuts', () => {
  for (const modifier of ['altKey', 'ctrlKey', 'metaKey']) {
    assert.equal(
      resolveSymbolReviewKeyboardCommand(
        key('1', { [modifier]: true }),
        symbols,
      ),
      null,
    );
    assert.equal(
      resolveSymbolReviewKeyboardCommand(
        key('Enter', { [modifier]: true }),
        symbols,
      ),
      null,
    );
  }
});

test('shortcut labels cover only the first nine symbols', () => {
  assert.equal(SYMBOL_REVIEW_SHORTCUT_SYMBOL_LIMIT, 9);
  assert.equal(symbolReviewShortcutLabel(0), '1');
  assert.equal(symbolReviewShortcutLabel(8), '9');
  assert.equal(symbolReviewShortcutLabel(9), null);
  assert.equal(symbolReviewShortcutLabel(-1), null);
});

test('non-DOM targets are not treated as text entry', () => {
  assert.equal(isSymbolReviewTextEntryTarget(null), false);
  assert.equal(isSymbolReviewTextEntryTarget({ tagName: 'INPUT' }), false);
});

test('workspace wires full screen mode and keyboard reassign flow', async () => {
  const source = await readFile(
    new URL(
      '../src/features/symbol-reviews/symbol-review-workspace.tsx',
      import.meta.url,
    ),
    'utf8',
  );
  const styles = await readFile(
    new URL(
      '../src/features/symbol-reviews/symbol-review-workspace.module.css',
      import.meta.url,
    ),
    'utf8',
  );
  assert.match(source, /'Zamknij pełny ekran' : 'Pełny ekran'/);
  assert.match(source, /fill=\{fullscreen\}/);
  assert.match(source, /window\.addEventListener\('keydown'/);
  assert.match(source, /isSymbolReviewTextEntryTarget\(event\.target\)/);
  assert.match(source, /setReassignTargetSymbolId\(command\.symbolId\)/);
  assert.match(source, /void previewOperation\('reassign'\)/);
  assert.match(source, /void startPreviewedOperation\(\)/);
  assert.match(styles, /\.workspaceFullscreen \{[\s\S]*position: fixed;/);
  assert.match(
    styles,
    /\.workspaceFullscreen \.pageWorkspace \{[\s\S]*min-height: 0;/,
  );
});
