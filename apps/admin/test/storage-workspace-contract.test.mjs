import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL('../src/features/storage/storage-workspace.tsx', import.meta.url),
  'utf8',
);

test('renders volume pressure and bounded inventory refresh as a durable job', () => {
  assert.match(source, /refreshImageStorageInventory/);
  assert.match(source, /api\.getJob\(jobId\)/);
  assert.match(source, /blokada zapisu/);
  assert.match(source, /wymagane czyszczenie/);
  assert.match(source, /ostrzeżenie/);
  assert.match(source, /bezpiecznie/);
  assert.match(source, /GiB/);
});

test('guards polling and requires the immutable preview before cleanup', () => {
  assert.match(source, /pollActive\.current/);
  assert.match(source, /preview\.manifestChecksumSha256/);
  assert.match(source, /preview\.previewToken/);
  assert.match(source, /confirmed: true/);
  assert.match(source, /Usuń bezpieczne dane/);
});

test('shows protected categories and remains in observe-only mode', () => {
  assert.match(source, /Tryb obserwacji/);
  assert.match(source, /Blokady ochronne/);
  assert.match(source, /Oryginały, cropy z referencjami i modele są chronione/);
});
