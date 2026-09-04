import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspace = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/selected-image-crop-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const viewer = await readFile(
  new URL(
    '../src/features/manual-image-selection/manual-image-viewer.tsx',
    import.meta.url,
  ),
  'utf8',
);
const parentWorkspace = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/semi-automatic-selection-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);

test('crop workspace is local and mounted below semi automatic selection', () => {
  assert.match(parentWorkspace, /<SelectedImageCropWorkspace \/>/u);
  assert.match(workspace, /Przytnij wybrane zdjęcia/u);
  assert.doesNotMatch(workspace, /AdminApiClient|fetch\(|jobId|apiBaseUrl/u);
});

test('crop review provides bounded viewer, progress and required shortcuts', () => {
  assert.match(workspace, /<ManualImageViewer/u);
  assert.match(workspace, /acceptedCount/u);
  assert.match(workspace, /event\.key === 'ArrowLeft'/u);
  assert.match(workspace, /event\.key === 'ArrowRight'/u);
  assert.match(workspace, /toLocaleLowerCase\('pl-PL'\) === 'f'/u);
  assert.match(workspace, /Zapisz ponownie/u);
  assert.match(workspace, /Resetuj cięcie/u);
  assert.match(workspace, /proposeSelectedImageCrop/u);
  assert.match(workspace, /Automatyczna propozycja/u);
  assert.match(workspace, /proposal\?\.crop/u);
});

test('shared viewer overlay is optional and preserves existing image rendering', () => {
  assert.match(viewer, /readonly imageOverlay\?: ReactNode/u);
  assert.match(viewer, /\{imageOverlay\}/u);
  assert.match(viewer, /state\.visibleImageUrl/u);
  assert.match(viewer, /manualPreviewWindow/u);
});

test('viewport state persists without storing image blobs', () => {
  assert.match(workspace, /scrollLeft: saved\.scrollLeft/u);
  assert.match(workspace, /scrollTop: saved\.scrollTop/u);
  assert.match(workspace, /zoom: saved\.zoom/u);
  assert.doesNotMatch(workspace, /indexedDB[\s\S]*Blob/u);
});
