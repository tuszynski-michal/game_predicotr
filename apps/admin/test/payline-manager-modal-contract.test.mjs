import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL('../src/features/rules/payline-manager-modal.tsx', import.meta.url),
  'utf8',
);

test('payline modal exposes code but not manually maintained name or display order', () => {
  assert.match(source, /Kod stabilny/);
  assert.match(source, /<strong>\{payline\.code\}<\/strong>/);
  assert.doesNotMatch(source, /payline\.name/);
  assert.doesNotMatch(source, /payline\.displayOrder/);
  assert.doesNotMatch(source, />Nazwa</);
  assert.doesNotMatch(source, />Kolejność</);
});
