import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL('../src/features/rules/rules-version-catalog.tsx', import.meta.url),
  'utf8',
);
const payoutSource = await readFile(
  new URL(
    '../src/features/rules/payout-computation-panel.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('rules UI exposes one current workspace and keeps technical history internal', () => {
  assert.match(source, /Bieżące reguły/);
  assert.match(source, /Rozpocznij edycję/);
  assert.match(source, /Wersjonowanie działa wewnętrznie/);
  assert.doesNotMatch(source, /Historia wersji/);
  assert.doesNotMatch(source, /\+ Nowy draft/);
});

test('rules workspace exposes explicit payout recomputation and progress', () => {
  assert.match(source, /PayoutComputationPanel/);
  assert.match(payoutSource, /Przelicz plansze/);
  assert.match(payoutSource, /payout-v2|PAYOUT_ALGORITHM_VERSION/);
  assert.match(payoutSource, /Wznów przeliczanie/);
  assert.match(payoutSource, /progress/);
});

test('rules creation always releases its submitting guard', () => {
  assert.match(
    source,
    /finally\s*\{\s*mutationInProgress\.current = false;\s*setIsSubmitting\(false\);\s*\}/,
  );
});

test('TASK-0931: payout editor labels trigger lengths as counts on the board', async () => {
  const modalSource = await readFile(
    new URL(
      '../src/features/rules/payout-rules-manager-modal.tsx',
      import.meta.url,
    ),
    'utf8',
  );
  const stateSource = await readFile(
    new URL('../src/features/rules/payout-rules-state.ts', import.meta.url),
    'utf8',
  );
  assert.match(stateSource, /sztuk na planszy/);
  assert.match(modalSource, /isSuperGameTriggerSymbol\(editingSymbol\) \? \(/);
  assert.match(
    modalSource,
    /countPayoutLengths\(\s*rulesVersion\.rows,\s*rulesVersion\.columns,?\s*\)/,
  );
  assert.match(modalSource, /payoutLengthLabel\(editingSymbol, matchLength\)/);
  assert.match(modalSource, /rulesVersion\.rows,\s*\);/);
  assert.doesNotMatch(modalSource, /Joker/);
});
