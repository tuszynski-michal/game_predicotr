import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL('../src/features/symbols/symbol-catalog.tsx', import.meta.url),
  'utf8',
);

test('uses the manual symbol catalog workflow without bootstrap or archival controls', () => {
  assert.match(source, />\s*Dodaj symbol\s*</);
  assert.match(source, />\s*Wild\s*</);
  assert.doesNotMatch(source, /Joker/);
  assert.match(source, /Brak zatwierdzonej grafiki referencyjnej/);
  assert.match(source, /<SymbolIdentityMetadata/);
  assert.match(source, />\s*Edytuj\s*</);
  assert.match(source, />\s*Usuń\s*</);
  assert.match(source, /<SymbolDeleteDialog/);
  assert.match(source, /error=\{deleteError\}/);
  assert.match(source, /Zależności blokujące usunięcie/);
  assert.doesNotMatch(source, /Bootstrap/);
  assert.doesNotMatch(source, /Archiwizuj/);
  assert.doesNotMatch(source, /imagePath: event/);
});

test('keeps every image tile actionable, including its question-mark placeholder', () => {
  assert.match(
    source,
    /aria-label={`Wybierz grafikę symbolu \$\{symbol\.name\}`}/,
  );
  assert.match(source, /className="symbolImageFallback">\s*\?/);
  assert.match(source, /onClick=\{\(\) => onImageSelection\(symbol\)\}/);
  assert.doesNotMatch(source, /disabled=\{symbol\.imagePath === null\}/);
});

test('opens the approved-crop picker and refreshes the catalog with its saved reference', () => {
  assert.match(source, /<SymbolImagePickerModal/);
  assert.match(source, /setImagePickerSymbolId\(symbol\.id\)/);
  assert.match(source, /upsertSymbol\(current, savedSymbol\)/);
});

test('TASK-0931: the symbol editor exposes Wild, the trigger checkbox and its count select', () => {
  assert.match(source, /name="isWildcard"/);
  assert.match(source, /Uruchamia supergrę/);
  assert.match(source, /name="triggersSuperGame"/);
  assert.match(source, /\{draft\.triggersSuperGame \? \(/);
  assert.match(source, /name="superGameTriggerCount"/);
  assert.match(source, /SUPER_GAME_TRIGGER_COUNT_OPTIONS\.map/);
  assert.match(source, /canEditSuperGameTrigger\(game, draft\)/);
  assert.match(source, /game=\{selectedGame\}/);
});
