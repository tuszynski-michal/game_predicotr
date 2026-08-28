import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspace = await readFile(
  new URL(
    '../src/features/grid-reviews/grid-review-workspace.tsx',
    import.meta.url,
  ),
  'utf8',
);
const editor = await readFile(
  new URL(
    '../src/features/grid-reviews/grid-review-editor.tsx',
    import.meta.url,
  ),
  'utf8',
);
const state = await readFile(
  new URL('../src/features/grid-reviews/grid-review-state.ts', import.meta.url),
  'utf8',
);
const gate = await readFile(
  new URL('../src/features/access/reviewer-access-gate.tsx', import.meta.url),
  'utf8',
);
const page = await readFile(
  new URL('../src/app/page.tsx', import.meta.url),
  'utf8',
);
const proxy = await readFile(
  new URL('../src/security/reviewer-proxy-policy.ts', import.meta.url),
  'utf8',
);

test('local grid workspace keeps remote reviewer on the restricted legacy path', () => {
  assert.match(gate, /gridValidationEnabled[\s\S]*GridReviewWorkspace/);
  assert.match(gate, /OperationalReviewWorkspace/);
  assert.match(page, /gridValidationEnabled=\{localMode\}/);
  assert.doesNotMatch(page, /REVIEWER_GRID_VALIDATION/);
  assert.doesNotMatch(proxy, /\/grid-reviews/);
  assert.doesNotMatch(proxy, /\/image-reviews\//);
});

test('grid workspace has bounded keyset navigation, filters, keyboard approval and submit lock', () => {
  assert.match(state, /Do walidacji/);
  assert.match(state, /Do poprawy/);
  assert.match(state, /Wszystkie/);
  assert.match(workspace, /afterCursor/);
  assert.match(workspace, /beforeCursor/);
  assert.match(workspace, /event\.key === 'Enter'/);
  assert.match(workspace, /event\.key\.toLowerCase\(\) === 'f'/);
  assert.match(workspace, /submitLock\.current/);
  assert.match(workspace, /moveAfterSuccess/);
  assert.doesNotMatch(workspace, /listSymbols/);
});

test('editor supports four-point topology-aware correction without overlay files', () => {
  assert.match(editor, /GRID_CORNER_LABELS\[draft\.length\]/);
  assert.match(editor, /onPointerDown=\{pointerDown\}/);
  assert.match(editor, /moveGridGeometryCorner/);
  assert.match(editor, /moveGridGeometry/);
  assert.match(editor, /Cofnij punkt/);
  assert.match(editor, /Resetuj/);
  assert.match(editor, /item\.gridColumns/);
  assert.match(editor, /item\.gridRows/);
  assert.match(editor, /previewGridReviewGeometry/);
  assert.match(editor, /saveGridReviewGeometry/);
  assert.doesNotMatch(editor, /upload|overlay.*(?:jpeg|jpg)/i);
});
