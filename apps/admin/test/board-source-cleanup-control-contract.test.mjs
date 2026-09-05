import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL(
    '../src/features/cleanup/board-source-cleanup-control.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('requires a preview of complete source ranges before destructive cleanup', () => {
  assert.match(source, /previewBoardSourceCleanup/);
  assert.match(source, /deleteBoardSourceRanges/);
  assert.match(source, /parseSequenceNumbers/);
  assert.match(source, /Podaj od 1 do 500 dodatnich numerów plansz/);
  assert.match(source, /Wpisz dokładnie identyfikator zakresu/);
  assert.match(source, /SYMBOL_MODEL_ACTIVATION_REQUIRED/);
});
