import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const panel = await readFile(
  new URL(
    '../src/features/imports/page-geometry-correction-panel.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('page geometry editor exposes ordered corners and exact reset', () => {
  assert.match(panel, /lewy górny.*prawy górny.*prawy dolny.*lewy dolny/s);
  assert.match(panel, />\s*Wyznacz 4 narożniki\s*</);
  assert.match(panel, />\s*Wyznacz 9 plansz osobno\s*</);
  assert.match(panel, />\s*Cofnij punkt\s*</);
  assert.match(panel, />\s*Reset\s*</);
  assert.match(panel, /setPageCorners\(initialPageCorners\)/);
  assert.match(panel, /setBoardOverrides\(initialBoardOverrides\)/);
  assert.match(panel, /beginBoardCornerPlacement/);
  assert.match(panel, /completePageGeometryBoardQuads/);
  assert.match(panel, /rząd.*kolumna/s);
});

test('saving a correction is separated from submitting the saved batch', () => {
  assert.match(panel, /Zapisz i przejdź dalej/);
  assert.match(panel, /Wyślij zapisane do weryfikacji/);
  assert.match(panel, /async function save\(\)[\s\S]*setSavedCount/);
  assert.match(
    panel,
    /async function submitSaved\(\)[\s\S]*await onSubmitSaved\(\)/,
  );
});

test('geometry editor uses the manual-selection fit model and bounded zoom', () => {
  assert.match(panel, /fitManualImageToViewport/);
  assert.match(panel, /MIN_GEOMETRY_ZOOM = 1/);
  assert.match(panel, /MAX_GEOMETRY_ZOOM = 30/);
  assert.match(panel, /GEOMETRY_ZOOM_STEP = 0\.25/);
  assert.match(panel, /Powiększenie zdjęcia geometrii/);
  assert.match(panel, /Przewijaj powiększony obraz w obu osiach/);
  assert.match(panel, /className="pageGeometryViewport" ref=\{viewportRef\}/);
});
