import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { cleanupCountLabel } from '../src/features/cleanup/cleanup-labels.ts';

test('cleanup explains retained recognition results in both existing previews', () => {
  assert.equal(
    cleanupCountLabel('grid_reinference_history_preserved'),
    'Zachowane wyniki ponownego rozpoznania',
  );
  assert.equal(
    cleanupCountLabel('grid_reinference_links_detached'),
    'Zdjęcia odłączane od zachowanych wyników',
  );
  assert.equal(cleanupCountLabel('existing_count'), 'existing_count');
  for (const file of [
    'cleanup-control.tsx',
    'board-source-cleanup-control.tsx',
  ]) {
    const source = readFileSync(
      new URL('../src/features/cleanup/' + file, import.meta.url),
      'utf8',
    );
    assert.match(source, /cleanupCountLabel\(entry.name\)/);
  }
  const board = readFileSync(
    new URL(
      '../src/features/cleanup/board-source-cleanup-control.tsx',
      import.meta.url,
    ),
    'utf8',
  );
  assert.match(board, /Wyniki ponownego rozpoznania zostaną zachowane/);
});
