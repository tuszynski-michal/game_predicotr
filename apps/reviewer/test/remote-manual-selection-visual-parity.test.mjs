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

test('remote workspace persists an explicit nine-layout range correction', async () => {
  const workspace = await readFile(workspacePath, 'utf8');
  const css = await readFile(reviewerCssPath, 'utf8');

  assert.match(workspace, /manualImageSelectionRangeButton/);
  assert.match(workspace, /openRangeEditor/);
  assert.match(workspace, /rangeEnd !== rangeStart \+ 8/);
  assert.match(workspace, /nextRangeStart: rangeStart/);
  assert.match(workspace, /await persistOperatorLocalManifest\(next\)/);
  assert.match(workspace, /interactionPaused \|\| rangeEditorOpen/);
  assert.match(css, /\.manualImageSelectionRangeEditor\s*\{/);
  assert.match(css, /\.manualImageSelectionRangeButton\s*\{/);
});

test('remote preview scrolls and restores both axes after layout', async () => {
  const workspace = await readFile(workspacePath, 'utf8');
  const css = await readFile(reviewerCssPath, 'utf8');

  assert.match(
    workspace,
    /pendingScrollRestoreOrdinal\.current = targetOrdinal/,
  );
  assert.match(
    workspace,
    /pendingScrollRestoreOrdinal\.current !== workspace\.currentIndex/,
  );
  assert.match(workspace, /pendingScrollRestoreOrdinal[\s\S]*!decoded/);
  assert.match(
    workspace,
    /animationFrame = window\.requestAnimationFrame\(restore\)/,
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
    /if \(pendingScrollRestoreOrdinal\.current === null\)[\s\S]*savedScrollLeft\.current =[\s\S]*savedScrollTop\.current =/,
  );
  assert.match(
    workspace,
    /const requestedScrollPosition = capturePreviewScroll\(\);[\s\S]*armPreviewScrollRestore\(nextCursorIndex\);[\s\S]*\.enqueue\(\(\) =>[\s\S]*acceptRequestedImage\([\s\S]*requestedScrollPosition[\s\S]*nextCursorIndex/,
  );
  assert.match(
    workspace,
    /savedScrollLeft\.current = requestedScrollPosition\.left;[\s\S]*savedScrollTop\.current = requestedScrollPosition\.top;[\s\S]*setBusy\(true\)/,
  );
  assert.match(
    workspace,
    /await store\.appendLocalWorkspaceDecision[\s\S]*setBatch\(nextBatch\)/,
  );
  assert.match(workspace, /gp\.remote-manual-selection\.scroll\.v1/);
  assert.match(workspace, /window\.localStorage\.setItem/);
  assert.match(workspace, /window\.addEventListener\('pagehide'/);
  assert.doesNotMatch(workspace, /setNaturalImageSize\(null\)/);
  assert.match(
    workspace,
    /\{previewUrl === null \? \([\s\S]*Ładowanie lokalnego JPEG-a/,
  );
  assert.match(
    css,
    /\.remoteManualPreviewViewport\s*\{[\s\S]*?justify-content:\s*flex-start;[\s\S]*?overflow-x:\s*auto;[\s\S]*?overflow-y:\s*auto;[\s\S]*?\}/,
  );
  assert.match(
    css,
    /\.remoteManualPreviewCanvas\s*\{[\s\S]*?flex:\s*0 0 auto;[\s\S]*?margin-inline:\s*auto;[\s\S]*?margin-block:\s*auto;[\s\S]*?\}/,
  );
  assert.match(
    css,
    /\.manualImageSelectionImageViewport\s*\{[\s\S]*?display:\s*flex;[\s\S]*?width:\s*100%;[\s\S]*?height:\s*100%;[\s\S]*?\}/,
  );
});

test('remote image is full width with visible zoom and local-only status above the workspace', async () => {
  const workspace = await readFile(workspacePath, 'utf8');
  const css = await readFile(reviewerCssPath, 'utf8');

  assert.doesNotMatch(workspace, /remoteManualSyncControls/);
  assert.ok(workspace.indexOf('Tryb lokalny operatora') >= 0);
  assert.doesNotMatch(workspace, /remoteManualSyncPanel/);
  assert.doesNotMatch(workspace, /<dt>|<dd>/);
  assert.match(
    workspace,
    /manualImageSelectionFilename[\s\S]*remoteManualShortcutHelp/,
  );
  assert.match(workspace, /onClick=\{\(\) => changeZoom\(25\)\}/);
  assert.match(
    css,
    /\.remoteManualWorkspaceGrid\s*\{[\s\S]*?display:\s*block;[\s\S]*?\}/,
  );
  assert.match(
    css,
    /\.remoteManualPreviewCanvas > img\s*\{[\s\S]*?max-width:\s*none;[\s\S]*?max-height:\s*none;[\s\S]*?\}/,
  );
  assert.match(
    css,
    /\.manualImageSelectionImageFrame\s*\{[\s\S]*?height:\s*calc\(64vh \+ 30px\);[\s\S]*?\}/,
  );
});

test('remote zoom uses local fit semantics and persists across images and reloads', async () => {
  const workspace = await readFile(workspacePath, 'utf8');

  assert.match(
    workspace,
    /readStoredZoom\(initialBatch\.sessionId, initialBatch\.batchId\)/,
  );
  assert.match(
    workspace,
    /const zoomedImageSize = fitManualImageToViewport\([\s\S]*zoom \/ 100/,
  );
  assert.match(
    workspace,
    /Math\.min\(3000, Math\.max\(100, currentPercent \+ delta\)\)/,
  );
  assert.match(workspace, /gp\.remote-manual-selection\.zoom\.v1/);
  assert.match(workspace, /const previewImage = useRef<HTMLImageElement>/);
  assert.match(workspace, /image\.complete/);
  assert.match(workspace, /image\.naturalHeight < 1/);
  assert.match(workspace, /image\.naturalWidth < 1/);
  assert.match(workspace, /ref=\{previewImage\}/);
  assert.match(
    workspace,
    /onLoad=\{\(event\) =>[\s\S]*captureNaturalImageSize\(event\.currentTarget\)/,
  );
  assert.doesNotMatch(workspace, /onLoadCapture=/);
  assert.doesNotMatch(workspace, /zoomState\.ordinal/);
});

test('remote acceptance does not drop a visible image while its load event settles', async () => {
  const workspace = await readFile(workspacePath, 'utf8');

  assert.match(
    workspace,
    /if \(previewUrl === null \|\| previewOrdinal !== current\.ordinal \|\| !decoded\)/,
  );
  assert.doesNotMatch(
    workspace,
    /if \(previewUrl === null \|\| previewOrdinal !== current\.ordinal\) \{/,
  );
  assert.doesNotMatch(
    workspace,
    /!canEdit \|\|[\s\S]{0,40}busyRef\.current \|\|[\s\S]{0,40}finalizingRef\.current/,
  );
  assert.match(
    workspace,
    /disabled=\{!canEdit \|\| hasConflict \|\| sourceReader === null\}/,
  );
  assert.match(
    workspace,
    /const activePreview = useRef<\{ ordinal: number; url: string \} \| null>/,
  );
  assert.match(
    workspace,
    /const previewChanged =[\s\S]*activePreview\.current\?\.ordinal !== workspace\.currentIndex[\s\S]*activePreview\.current\.url !== selected/,
  );
  assert.match(
    workspace,
    /if \(!cancelled && previewChanged\) \{[\s\S]*setDecoded\(false\);[\s\S]*setPreviewOrdinal\(workspace\.currentIndex\);[\s\S]*setPreviewUrl\(selected\)/,
  );
  assert.doesNotMatch(workspace, /setNaturalImageSize\(null\)/);
  assert.match(workspace, /\{previewUrl === null \? \(/);
  assert.doesNotMatch(
    workspace,
    /\{previewUrl === null \|\| previewOrdinal !== workspace\.currentIndex \? \(/,
  );
});
