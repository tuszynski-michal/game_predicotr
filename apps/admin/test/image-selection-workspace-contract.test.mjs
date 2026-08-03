import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspaceSource = await readFile(
  new URL(
    '../src/features/image-selection/image-selection-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const catalogSource = await readFile(
  new URL('../src/features/catalog/catalog-workspace.tsx', import.meta.url),
  'utf8',
);
const styleSource = await readFile(
  new URL('../src/app/globals.css', import.meta.url),
  'utf8',
);

test('uses a browser-native directory picker directly from the owner action', () => {
  assert.match(workspaceSource, /folderInputRef\.current\?\.click\(\)/);
  assert.match(workspaceSource, /node\.webkitdirectory = true/);
  assert.match(workspaceSource, /type="file"/);
  assert.match(workspaceSource, /multiple/);
  assert.doesNotMatch(workspaceSource, /FileReader|arrayBuffer\(/);
});

test('shows bounded upload recovery with file and byte progress', () => {
  assert.match(workspaceSource, /progress\.uploadedFiles/);
  assert.match(workspaceSource, /progress\.uploadedBytes/);
  assert.match(workspaceSource, /Ponów brakujące pliki/);
  assert.match(workspaceSource, /Anuluj staging/);
  assert.match(workspaceSource, /30_000/);
});

test('isolates image selection state by active game and keeps four tiles responsive', () => {
  assert.match(catalogSource, /key=\{activeGame\.id\}/);
  assert.match(catalogSource, /gameId=\{activeGame\.id\}/);
  assert.match(
    styleSource,
    /grid-template-columns: repeat\(4, minmax\(0, 1fr\)\)/,
  );
  assert.match(
    styleSource,
    /grid-template-columns: repeat\(2, minmax\(0, 1fr\)\)/,
  );
  assert.match(styleSource, /\.imageSelectionWorkspace\s*\{[^}]*min-width: 0/s);
});

test('hands a verified output to the explicit import step without starting it', () => {
  assert.match(workspaceSource, /handoffImageSelection\(run\.id\)/);
  assert.match(workspaceSource, /Przekaż do Importu layoutów/);
  assert.match(workspaceSource, /run\.outputManifestSha256 === null/);
  assert.match(catalogSource, /section: 'imports'/);
  assert.match(catalogSource, /initialHandoff=/);
});
