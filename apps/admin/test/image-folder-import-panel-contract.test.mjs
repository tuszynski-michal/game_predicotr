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
  assert.match(panelSource, /utworzony — oczekuje na worker/);
  assert.match(panelSource, /Usuń nieużywany staging/);
});

test('provides styled actions and accessible import help', () => {
  assert.match(panelSource, /className="importActionToolbar"/);
  assert.match(panelSource, /className="secondaryButton"/);
  assert.match(panelSource, /aria-label="Pomoc dotycząca akcji importu"/);
  assert.match(panelSource, /role="tooltip"/);
  assert.match(panelSource, /Co robią te akcje\?/);
  assert.match(globalStyles, /\.importActionButtons \{/);
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
