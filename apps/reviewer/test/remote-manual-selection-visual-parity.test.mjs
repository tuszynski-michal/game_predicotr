import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspacePath = new URL(
  '../src/features/manual-selection/remote-manual-selection-workspace.tsx',
  import.meta.url,
);
const reviewerCssPath = new URL('../src/app/reviewer.css', import.meta.url);

test('remote workspace reuses the local manual-selection visual system', async () => {
  const workspace = await readFile(workspacePath, 'utf8');

  assert.match(workspace, /manualImageSelectionWorkspace/);
  assert.match(workspace, /manualImageSelectionHeader/);
  assert.match(workspace, /manualImageSelectionViewerToolbar/);
  assert.match(workspace, /manualImageSelectionViewer/);
  assert.match(workspace, /manualImageSelectionImageFrame/);
  assert.match(workspace, /manualImageSelectionImageCanvas/);
  assert.match(workspace, /manualImageSelectionNav/);
  assert.match(workspace, /manualImageSelectionActions/);
  assert.doesNotMatch(workspace, /type="range"/);
});

test('remote preview stays horizontally centered and restores vertical scroll after layout', async () => {
  const workspace = await readFile(workspacePath, 'utf8');
  const css = await readFile(reviewerCssPath, 'utf8');

  assert.match(workspace, /pendingScrollRestore\.current = true/);
  assert.match(workspace, /window\.requestAnimationFrame/);
  assert.match(
    workspace,
    /viewport\.current\.scrollTop = savedScrollTop\.current/,
  );
  assert.match(
    workspace,
    /if \(!pendingScrollRestore\.current\)[\s\S]*savedScrollTop\.current =/,
  );
  assert.match(
    css,
    /\.remoteManualPreviewViewport\s*\{[\s\S]*?overflow-x:\s*hidden;[\s\S]*?overflow-y:\s*auto;[\s\S]*?\}/,
  );
  assert.match(
    css,
    /\.remoteManualPreviewCanvas\s*\{[\s\S]*?flex:\s*0 0 auto;[\s\S]*?margin-block:\s*auto;[\s\S]*?\}/,
  );
});
