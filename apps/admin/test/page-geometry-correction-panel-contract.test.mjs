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
const styles = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
  'utf8',
);

test('page geometry editor exposes ordered corners and exact reset', () => {
  assert.match(panel, /lewy górny.*prawy górny.*prawy dolny.*lewy dolny/s);
  assert.match(panel, />\s*Wyznacz 4 narożniki\s*</);
  assert.match(panel, /Wyznacz \{expectedBoardCount\} plansz osobno/);
  assert.match(panel, />\s*Cofnij punkt\s*</);
  assert.match(panel, />\s*Reset\s*</);
  assert.match(panel, /setPageCorners\(initialPageCorners\)/);
  assert.match(panel, /setBoardOverrides\(initialBoardOverrides\)/);
  assert.match(panel, /beginBoardCornerPlacement/);
  assert.match(panel, /completePageGeometryBoardQuads/);
  assert.match(panel, /showAllBoardCorners\(completeQuads\)/);
  assert.match(panel, /Wszystkie plansze — 36 narożników/);
  assert.match(panel, /rząd.*kolumna/s);
  assert.match(panel, /source\?\.expectedBoardCount \?\? PAGE_BOARD_COUNT/);
  assert.match(panel, /quads\.length !== expectedBoardCount/);
});

test('saving a correction is separated from submitting the saved batch', () => {
  assert.match(panel, /Zapisz i przejdź dalej/);
  assert.match(panel, /Wyślij zapisane do weryfikacji/);
  assert.match(panel, /async function save\(\)[\s\S]*setSavedCount/);
  assert.match(
    panel,
    /async function submitSaved\(\)[\s\S]*await onSubmitSaved\(\)/,
  );
  assert.match(panel, /Liczniki dotyczą zdjęć źródłowych/);
  assert.match(panel, /aktualizacja już zarejestrowanej geometrii/);
  assert.match(panel, /nie zwiększy tego licznika/);
});

test('geometry editor uses the manual-selection fit model and bounded zoom', () => {
  assert.match(panel, /fitManualImageToViewport/);
  assert.match(panel, /MIN_GEOMETRY_ZOOM = 1/);
  assert.match(panel, /MAX_GEOMETRY_ZOOM = 30/);
  assert.match(panel, /GEOMETRY_ZOOM_STEP = 0\.25/);
  assert.match(panel, /Powiększenie zdjęcia geometrii/);
  assert.match(panel, /Przewijaj powiększony obraz w obu osiach/);
  assert.match(panel, /className="pageGeometryViewport" ref=\{viewportRef\}/);
  assert.match(panel, /HANDLE_SCREEN_RADIUS = 7/);
  assert.match(
    panel,
    /HANDLE_SCREEN_RADIUS \* imageSize\.width\) \/ zoomedCanvasSize\.width/,
  );
  assert.doesNotMatch(panel, /r=\{HANDLE_RADIUS\}/);
  assert.match(
    styles,
    /\.pageGeometryCorrectionGrid\s*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\)/s,
  );
});

test('geometry editor hides the system proposal while placing manual geometry and previews 5x3 cuts', () => {
  assert.match(
    panel,
    /manualPlacementActive\s*=\s*cornerPlacement !== null \|\| boardCornerPlacement !== null/,
  );
  assert.match(panel, /\{!manualPlacementActive\s*\? quads\.map/);
  assert.match(panel, /pageGeometrySymbolCutLines\(quad\)/);
  assert.match(panel, /pageGeometrySymbolCutPlacement/);
  assert.match(panel, /potencjalny podział na\s*symbole 5 × 3/);
  assert.match(panel, /komplet \$\{expectedBoardCount\} edytowalnych plansz/);
});

test('geometry editor labels a fallback template and exposes stored diagnostics', () => {
  assert.match(panel, /Nie wykryto geometrii — ustaw plansze ręcznie/);
  assert.match(panel, /roboczym szablonem edytora/);
  assert.match(panel, /Szczegółowa przyczyna nie została zapisana/);
  assert.match(panel, /registrationDiagnostics\?\.bestAttempt/);
  assert.match(panel, /geometryOrigin === 'manual_override'/);
  assert.match(panel, /Reset przywraca dokładnie\s*ten zapis/s);
  assert.match(styles, /\.geometryOriginNoticeWarning/);
});
