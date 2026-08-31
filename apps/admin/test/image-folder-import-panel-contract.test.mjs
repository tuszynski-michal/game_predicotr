import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const panelSource = await readFile(
  new URL(
    '../src/features/imports/image-folder-import-panel.tsx',
    import.meta.url,
  ),
  'utf8',
);
const modePickerSource = await readFile(
  new URL(
    '../src/features/imports/board-cell-processing-mode-picker.tsx',
    import.meta.url,
  ),
  'utf8',
);
const globalStyles = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
  'utf8',
);
const workspaceSource = await readFile(
  new URL('../src/features/catalog/catalog-workspace.tsx', import.meta.url),
  'utf8',
);

test('distinguishes the active import operation from a disabled prerequisite', () => {
  assert.match(panelSource, /type ImportAction =/);
  assert.match(panelSource, /activeAction === 'choose-folder'/);
  assert.match(panelSource, /activeAction === 'start-import'/);
  assert.match(panelSource, /activeAction === 'refresh-status'/);
  assert.match(panelSource, /activeAction === 'reprocess-import'/);
  assert.match(panelSource, /finally \{\s*setActiveAction\(null\)/);
  assert.match(globalStyles, /button:disabled \{\s*cursor: not-allowed;/);
  assert.match(
    globalStyles,
    /button\[aria-busy='true'\] \{\s*cursor: progress;/,
  );
});

test('reports incomplete board creation and offers managed-original reprocessing', () => {
  assert.match(panelSource, /Pipeline zdjęć:/);
  assert.match(panelSource, /Silnik cięcia plansz:/);
  assert.match(panelSource, /boardCellProcessingJobLabel/);
  assert.match(panelSource, /Wynik jest niekompletny/);
  assert.match(panelSource, /Przetwórz ponownie z oryginałów/);
  assert.match(panelSource, /reprocessImageFolderImport/);
});

test('recovers finalized staging and requires a checksum-bound preflight start', () => {
  assert.match(panelSource, /listReadyBrowserImageSelections/);
  assert.match(panelSource, /previewReadyBrowserImageImport/);
  assert.match(panelSource, /startReadyBrowserImageImport/);
  assert.match(panelSource, /Gotowy staging do wznowienia/);
  assert.match(panelSource, /Rozpocznij import z raportu/);
  assert.match(panelSource, /startBrowserPageGeometryPreflight/);
  assert.match(panelSource, /preflightResult\.data\.geometryPreflightRequired/);
  assert.match(panelSource, /result\.data\.geometryPreflightRequired/);
  assert.match(panelSource, /Każda pozycja oznacza jedno zdjęcie/);
  assert.match(panelSource, /Importuj rozpoznane strony/);
  assert.match(panelSource, /BoardCellProcessingModePicker/);
  assert.match(panelSource, /jobMatchesBoardCellProcessingMode/);
  assert.match(panelSource, /Rozpocznij import v20 z raportu/);
  assert.match(
    panelSource,
    /Ręczna korekta zdjęć geometrii — zostaw na\s+koniec/,
  );
  assert.match(panelSource, /zarejestrowane zdjęcia/);
  assert.doesNotMatch(panelSource, /Import jest zablokowany/);
  assert.match(panelSource, /utworzony — oczekuje na worker/);
  assert.match(panelSource, /Usuń nieużywany staging/);
  assert.match(panelSource, /Import plansz z folderu/);
});

test('offers only stable v20 and safe structured shadow per game', () => {
  assert.match(modePickerSource, /wyłącznie nowych importów tej gry/);
  assert.match(modePickerSource, /v20 — geometria i cropy v19/);
  assert.match(modePickerSource, /nowy silnik w cieniu/);
  assert.match(modePickerSource, /nie aktywuje Geometry v2 produkcyjnie/);
  assert.match(modePickerSource, /Nie ma fallbacku do\s*v18/);
  assert.doesNotMatch(modePickerSource, /jawny opt-in/);
  assert.doesNotMatch(panelSource, /verifiedV19Confirmed/);
  assert.doesNotMatch(panelSource, /boardCellProcessingStartAllowed/);
  assert.ok(
    panelSource.indexOf('<BoardCellProcessingModePicker') <
      panelSource.indexOf('Gotowy staging do wznowienia'),
  );
  assert.match(
    panelSource,
    /className="secondaryButton"\s*disabled=\{busy \|\| enginePolicy === null\}[\s\S]*?'Wybierz folder'/,
  );
  assert.match(panelSource, /Raport stagingu odświeżono/);
});

test('provides styled actions and accessible import help', () => {
  assert.match(panelSource, /className="importActionToolbar"/);
  assert.match(panelSource, /className="secondaryButton"/);
  assert.match(panelSource, /aria-label="Pomoc dotycząca akcji importu"/);
  assert.match(panelSource, /role="tooltip"/);
  assert.match(panelSource, /Co robią te akcje\?/);
  assert.match(globalStyles, /\.importActionButtons \{/);
  assert.match(globalStyles, /\.boardCellProcessingModePicker \{/);
  assert.match(globalStyles, /\.importActionHelp:focus-within/);
});

test('orders import actions by workflow priority', () => {
  const toolbarStart = panelSource.indexOf('className="importActionButtons"');
  const toolbarEnd = panelSource.indexOf('className="importActionHelp"');
  const toolbarSource = panelSource.slice(toolbarStart, toolbarEnd);

  assert.ok(toolbarStart >= 0);
  assert.ok(toolbarEnd > toolbarStart);
  assert.ok(
    toolbarSource.indexOf('Rozpocznij import') <
      toolbarSource.indexOf('Wybierz folder'),
  );
  assert.ok(
    toolbarSource.indexOf('Wybierz folder') <
      toolbarSource.indexOf('Odśwież status'),
  );
});

test('contains completeness and source controls inside responsive components', () => {
  assert.match(panelSource, /className="importCompletenessCard"/);
  assert.match(panelSource, /className="importMetrics"/);
  assert.match(panelSource, /className="importMissingSequenceChips"/);
  assert.match(panelSource, /className="importSourceControls"/);
  assert.match(panelSource, /className="importCompactList"/);
  assert.match(globalStyles, /\.importMissingSequenceChips \{/);
  assert.match(globalStyles, /\.importSourceControls \{/);
  assert.match(
    globalStyles,
    /\.importMetrics,\s*\.importSourceControls \{\s*grid-template-columns: 1fr;/,
  );
});

test('isolates folder selection state when the active game changes', () => {
  assert.match(
    workspaceSource,
    /<ImageFolderImportPanel[\s\S]*gameId=\{activeGame\.id\}[\s\S]*key=\{activeGame\.id\}/,
  );
});

test('uses the browser-native directory input without a blocking OS helper', () => {
  assert.match(panelSource, /node\.webkitdirectory = true/);
  assert.match(panelSource, /node\.setAttribute\('webkitdirectory', ''\)/);
  assert.match(panelSource, /type="file"/);
  assert.match(panelSource, /uploadImageFolder/);
  assert.match(panelSource, /Przesyłanie/);
  assert.doesNotMatch(panelSource, /Otwieranie…/);
  assert.doesNotMatch(panelSource, /selectImageFolder/);
});
