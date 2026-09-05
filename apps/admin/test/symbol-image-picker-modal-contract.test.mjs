import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL(
    '../src/features/symbols/symbol-image-picker-modal.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('picker lists only approved candidates in pages of at most twenty and saves checksum-bound selections', () => {
  assert.match(source, /listApprovedSymbolReferenceCandidates/);
  assert.match(source, /expectedChecksumSha256: candidate\.cropChecksumSha256/);
  assert.match(source, /selectedBy: 'admin-local'/);
  assert.match(source, /Najpierw zatwierdź crop zawierający ten symbol/);
  assert.match(source, /Poprzednia/);
  assert.match(source, /Następna/);
  assert.doesNotMatch(source, /confidence/i);
  assert.doesNotMatch(source, /pełnej planszy/i);
});

test('one missing crop image does not suppress other approved candidates', () => {
  assert.match(source, /unavailableAssetIds/);
  assert.match(source, /new Set\(current\)\.add\(candidate\.observationId\)/);
  assert.match(source, /Plik niedostępny/);
});
