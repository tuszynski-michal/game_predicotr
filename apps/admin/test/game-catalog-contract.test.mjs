import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL('../src/features/games/game-catalog.tsx', import.meta.url),
  'utf8',
);

test('game catalog exposes status filters and an explicit restore action', () => {
  assert.match(source, /game-filter-\$\{status\}/);
  assert.match(source, /Przywróć jako szkic/);
  assert.match(source, /GamesFilteredEmpty/);
});

test('game catalog does not expose physical deletion', () => {
  assert.doesNotMatch(source, />\s*Usuń\s*</);
  assert.doesNotMatch(source, /deleteGame/);
});
