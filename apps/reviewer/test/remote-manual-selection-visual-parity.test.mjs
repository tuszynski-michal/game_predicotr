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

test('remote preview scrolls and restores both axes after layout', async () => {
  const workspace = await readFile(workspacePath, 'utf8');
  const css = await readFile(reviewerCssPath, 'utf8');

  assert.match(workspace, /pendingScrollRestore\.current = true/);
  assert.match(
    workspace,
    /window\.requestAnimationFrame\(\(\) => \{[\s\S]*window\.requestAnimationFrame/,
  );
  assert.match(
    workspace,
    /viewport\.current\.scrollLeft = savedScrollLeft\.current/,
  );
  assert.match(
    workspace,
    /viewport\.current\.scrollTop = savedScrollTop\.current/,
  );
  assert.match(
    workspace,
    /if \(!pendingScrollRestore\.current\)[\s\S]*savedScrollLeft\.current =[\s\S]*savedScrollTop\.current =/,
  );
  assert.match(
    css,
    /\.remoteManualPreviewViewport\s*\{[\s\S]*?justify-content:\s*flex-start;[\s\S]*?overflow-x:\s*auto;[\s\S]*?overflow-y:\s*auto;[\s\S]*?\}/,
  );
  assert.match(
    css,
    /\.remoteManualPreviewCanvas\s*\{[\s\S]*?flex:\s*0 0 auto;[\s\S]*?margin-inline:\s*auto;[\s\S]*?margin-block:\s*auto;[\s\S]*?\}/,
  );
});

test('remote image is full width with visible zoom and controls above the workspace', async () => {
  const workspace = await readFile(workspacePath, 'utf8');
  const css = await readFile(reviewerCssPath, 'utf8');

  assert.ok(
    workspace.indexOf('remoteManualSyncControls') <
      workspace.indexOf('remoteManualWorkspaceHeader'),
  );
  assert.doesNotMatch(workspace, /remoteManualSyncPanel/);
  assert.doesNotMatch(workspace, /<dt>|<dd>/);
  assert.match(
    workspace,
    /manualImageSelectionFilename[\s\S]*remoteManualShortcutHelp/,
  );
  assert.match(
    workspace,
    /onClick=\{\(\) => setZoom\(\(value\) => Math\.min\(3000, value \+ 25\)\)\}/,
  );
  assert.match(
    css,
    /\.remoteManualWorkspaceGrid\s*\{[\s\S]*?display:\s*block;[\s\S]*?\}/,
  );
  assert.match(
    css,
    /\.remoteManualPreviewCanvas > img\s*\{[\s\S]*?max-width:\s*none;[\s\S]*?max-height:\s*none;[\s\S]*?\}/,
  );
});
