import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspace = await readFile(
  new URL(
    '../src/features/v7-label-geometry/v7-label-geometry-calibration-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const store = await readFile(
  new URL(
    '../src/features/v7-label-geometry/v7-label-geometry-calibration-store.ts',
    import.meta.url,
  ),
  'utf8',
);
const navigation = await readFile(
  new URL('../src/features/catalog/admin-navigation-state.ts', import.meta.url),
  'utf8',
);
const catalog = await readFile(
  new URL('../src/features/catalog/catalog-workspace.tsx', import.meta.url),
  'utf8',
);

test('the calibration screen has only calibration case choices and no holdout control', () => {
  assert.match(workspace, /id: 'small_777'/);
  assert.match(workspace, /id: 'occluded_777'/);
  assert.doesNotMatch(workspace, /id: 'reels_test'/);
  assert.match(workspace, /geometryFamilyId: GEOMETRY_FAMILY_ID/);
  assert.match(workspace, /corpusCaseIds: \[\.\.\.selectedCaseIds\]/);
});

test('the screen uses a checksum-bound Blob asset and click coordinates from the image itself', () => {
  assert.match(workspace, /getV7LabelGeometryCalibrationSourceAsset/);
  assert.match(workspace, /result\.data instanceof Blob/);
  assert.match(workspace, /URL\.createObjectURL/);
  assert.match(workspace, /URL\.revokeObjectURL/);
  assert.match(workspace, /event\.currentTarget\.getBoundingClientRect\(\)/);
  assert.match(workspace, /normaliseV7LabelGeometryPoint/);
  assert.match(workspace, /isV7LabelGeometryPointInsideServerBounds\(point\)/);
  assert.match(workspace, /assetRef\.current\?\.key !== expectedAssetKey/);
  assert.match(workspace, /asset\.key === activeAssetKey/);
  assert.match(workspace, /Numer zasłonięty \/ nieczytelny/);
  assert.match(workspace, /kind: 'unavailable'/);
});

test('a durable queue serializes clicks, stops persistently, and never rebases', () => {
  assert.match(workspace, /await store\.appendOperation\(operation\)/);
  assert.match(workspace, /await withQueueTransition\(async \(\) => \{/);
  assert.match(workspace, /replaceQueue\(next\)[\s\S]*void flushQueue\(\)/);
  assert.match(workspace, /nextV7LabelGeometryOperation\(currentQueue\)/);
  assert.match(workspace, /await store\.removeHead/);
  assert.match(workspace, /toV7LabelGeometrySessionMutation\(head\)/);
  assert.match(workspace, /V7_CALIBRATION_SESSION_REVISION_CONFLICT/);
  assert.match(workspace, /queueStoppedReason: restoredQueue\.stoppedReason/);
  assert.match(workspace, /const currentView = viewRef\.current/);
  assert.match(workspace, /discardingRef\.current = true/);
  assert.match(workspace, /discardingRef\.current \|\|/);
  assert.match(workspace, /captureGroupDrafts\.get\(activeSource\.sourceId\)/);
  assert.match(workspace, /key=\{activeSource\?\.sourceId \?\? 'none'\}/);
  assert.match(workspace, /Porzuć niepotwierdzone/);
  assert.match(store, /DATABASE_NAME = 'game-predictor-v7-label-geometry-calibration'/);
  assert.match(store, /QUEUE_STORE = 'queue'/);
  assert.match(store, /VIEW_STORE = 'views'/);
  assert.doesNotMatch(store, /FileSystemDirectoryHandle|Blob|ImageBitmap/);
});

test('Admin navigation exposes the standalone calibration workspace', () => {
  assert.match(navigation, /'v7-label-geometry'/);
  assert.match(catalog, /Kalibracja etykiet V7/);
  assert.match(catalog, /V7LabelGeometryCalibrationWorkspace/);
});
