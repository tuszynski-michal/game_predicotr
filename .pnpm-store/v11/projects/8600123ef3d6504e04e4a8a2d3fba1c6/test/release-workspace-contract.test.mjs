import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const panelSource = await readFile(
  new URL('../src/features/releases/release-panel.tsx', import.meta.url),
  'utf8',
);
const catalogSource = await readFile(
  new URL('../src/features/catalog/catalog-workspace.tsx', import.meta.url),
  'utf8',
);

test('uses one controlled game and read-only automatic release sources', () => {
  assert.match(panelSource, /Jedna kontrolowana gra/);
  assert.match(panelSource, /selectControlledReleaseGame/);
  assert.match(panelSource, /releaseSourceSummary/);
  assert.match(panelSource, /createAndStartRelease/);
  assert.match(panelSource, /Utwórz i uruchom wydanie/);
  assert.doesNotMatch(panelSource, /ReleaseSourceRow/);
  assert.doesNotMatch(panelSource, /type="checkbox"/);
});

test('keeps history collapsible and delegates full job details', () => {
  assert.match(panelSource, /<details className="releaseHistoryDisclosure"/);
  assert.match(panelSource, /Pokaż w Jobach/);
  assert.match(
    catalogSource,
    /onOpenJobs=\{\(\) => selectWorkspace\('jobs'\)\}/,
  );
});
