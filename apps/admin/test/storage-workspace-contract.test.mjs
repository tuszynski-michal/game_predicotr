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

const cropPanel = await readFile(
  new URL('../src/features/storage/source-crop-panel.tsx', import.meta.url),
  'utf8',
);

test('mounts the photo crop panel without replacing inventory or cleanup', () => {
  assert.match(source, /<SourceCropPanel apiBaseUrl=\{apiBaseUrl\} \/>/);
  assert.match(source, /Przygotuj raport czyszczenia/);
  assert.match(source, /startStorageGcRun/);
});

test('crop panel separates deletion, warns about missing backup and gates start', () => {
  assert.match(cropPanel, /Przycinanie zdjęć/);
  assert.match(cropPanel, /Usuń oryginały przyciętych zdjęć/);
  assert.match(cropPanel, /Brak kopii zdjęć — operacji nie można cofnąć/);
  assert.match(cropPanel, /canStartRun\(run, acknowledged\)/);
  assert.match(cropPanel, /type="checkbox"/);
  assert.match(cropPanel, /role="dialog"/);
  assert.doesNotMatch(cropPanel, /fetch\(/);
});

const cropPanelStyles = await readFile(
  new URL(
    '../src/features/storage/source-crop-panel.module.css',
    import.meta.url,
  ),
  'utf8',
);

test('crop panel selects use the dark, opaque Admin select style', () => {
  assert.match(
    cropPanelStyles,
    /\.field select \{[^}]*background: #0b1524;[^}]*color-scheme: dark;/,
  );
  assert.match(
    cropPanelStyles,
    /\.field select option \{[^}]*background: #0b1524;[^}]*color: #f8fafc;/,
  );
  assert.match(cropPanel, /setGames\(selectableGames\(gameList\)\)/);
});
