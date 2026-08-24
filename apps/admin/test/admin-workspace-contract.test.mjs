import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspaceSource = await readFile(
  new URL('../src/features/catalog/catalog-workspace.tsx', import.meta.url),
  'utf8',
);
const shellSource = await readFile(
  new URL('../src/components/admin-shell.tsx', import.meta.url),
  'utf8',
);

test('preserves the three v0.2 workspaces and adds v0.4 image selection', () => {
  assert.match(workspaceSource, /Zarządzanie grami/);
  assert.match(workspaceSource, /Wersje Android/);
  assert.match(workspaceSource, /Joby/);
  assert.match(workspaceSource, /Selekcja zdjęć/);
  assert.match(workspaceSource, /id: 'image-selection'/);
  assert.match(workspaceSource, /WORKSPACE_OPTIONS/);
});

test('uses a single controlled game context for dependent sections', () => {
  assert.match(workspaceSource, /selectedGameId=\{navigation\.gameId\}/);
  assert.match(workspaceSource, /gameId=\{activeGame\.id\}/);
  assert.match(workspaceSource, /aria-expanded=\{expanded\}/);
  assert.doesNotMatch(shellSource, /href="#symbols"/);
  assert.doesNotMatch(shellSource, /href="#jobs"/);
});

test('keeps local manual image selection independent from game context', () => {
  assert.match(
    workspaceSource,
    /<ManualImageSelectionWorkspace apiBaseUrl=\{apiBaseUrl\} \/>/,
  );
  assert.doesNotMatch(
    workspaceSource,
    /Ręczna selekcja zapisuje sesję w kontekście wybranej gry/,
  );
});

test('does not expose duplicate Dataset or Manual Review workspaces', () => {
  assert.doesNotMatch(workspaceSource, /DatasetCatalog/);
  assert.doesNotMatch(workspaceSource, /ReviewWorkspace/);
  assert.doesNotMatch(workspaceSource, /Manual Review/i);
  assert.match(workspaceSource, /ImageFolderImportPanel/);
  assert.match(workspaceSource, /ReviewerAccessLauncher/);
  assert.match(workspaceSource, /ModelQualityWorkspace/);
  assert.match(workspaceSource, /Jakość rozpoznawania/);
});

test('keeps destructive game cleanup after every ordinary game section', () => {
  const gameSectionsIndex = workspaceSource.indexOf(
    '{GAME_SECTION_OPTIONS.map',
  );
  const cleanupIndex = workspaceSource.indexOf('<CleanupControl');

  assert.notEqual(gameSectionsIndex, -1);
  assert.notEqual(cleanupIndex, -1);
  assert.ok(cleanupIndex > gameSectionsIndex);
});

test('mounts only the expanded game section to avoid hidden request storms', () => {
  for (const section of [
    'imports',
    'symbols',
    'rules',
    'reviews',
    'model-quality',
  ]) {
    assert.match(
      workspaceSource,
      new RegExp(`expanded && section\\.id === '${section}'`),
    );
  }
});
