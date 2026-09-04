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
const actions = await readFile(
  new URL(
    '../src/features/grid-reviews/grid-review-actions.ts',
    import.meta.url,
  ),
  'utf8',
);
const gate = await readFile(
  new URL('../src/features/access/reviewer-access-gate.tsx', import.meta.url),
  'utf8',
);
const localWorkspace = await readFile(
  new URL(
    '../src/features/access/local-reviewer-workspace.tsx',
    import.meta.url,
  ),
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
const reviewerCss = await readFile(
  new URL('../src/app/reviewer.css', import.meta.url),
  'utf8',
);

test('grid reviewer owns the dark application foundation and styled controls', () => {
  assert.match(reviewerCss, /:root\s*\{[\s\S]*--background:\s*#07101d/);
  assert.match(reviewerCss, /color-scheme:\s*dark/);
  assert.match(reviewerCss, /button\s*\{[\s\S]*appearance:\s*none/);
  assert.match(reviewerCss, /\.gridReviewHeader\s*\{[\s\S]*background:/);
  assert.match(reviewerCss, /\.gridReviewActions\s*\{[\s\S]*background:/);
});

test('local grid workspace keeps remote reviewer on the restricted legacy path', () => {
  assert.match(gate, /gridValidationEnabled[\s\S]*LocalReviewerWorkspace/);
  assert.match(gate, /OperationalReviewWorkspace/);
  assert.match(localWorkspace, /GridReviewWorkspace/);
  assert.match(localWorkspace, /OperationalReviewWorkspace/);
  assert.match(localWorkspace, /listPendingBoardCellGeometry/);
  assert.match(localWorkspace, /Niepełne siatki do ręcznej korekty/);
  assert.match(page, /gridValidationEnabled=\{localMode\}/);
  assert.doesNotMatch(page, /REVIEWER_GRID_VALIDATION/);
  assert.doesNotMatch(proxy, /\/grid-reviews/);
  assert.doesNotMatch(proxy, /\/image-reviews\//);
});

test('grid workspace groups active slots by source and guards whole-image actions', () => {
  assert.match(state, /Do walidacji/);
  assert.match(state, /Do poprawy/);
  assert.match(state, /Wszystkie/);
  assert.match(workspace, /afterCursor/);
  assert.match(workspace, /beforeCursor/);
  assert.match(workspace, /event\.key === 'Enter'/);
  assert.match(workspace, /event\.key\.toLowerCase\(\) === 'f'/);
  assert.match(workspace, /submitLock\.current/);
  assert.match(workspace, /moveSource\('next'\)/);
  assert.match(workspace, /approveSource/);
  assert.match(workspace, /approveGridReviewSource/);
  assert.match(workspace, /rejectSource/);
  assert.match(workspace, /sourceImageId/);
  assert.match(workspace, /gridReviewSourceStats/);
  assert.match(workspace, /key=\{anchorItem\.sourceImageId\}/);
  assert.doesNotMatch(workspace, /sourceImageId\}:\$\{selectedReviewItemId/);
  assert.doesNotMatch(workspace, /listSymbols/);
});

test('editor overlays every active slot and supports bounded A/B correction without overlay files', () => {
  assert.match(editor, /GRID_CORNER_LABELS\[activeDraft\.length\]/);
  assert.match(editor, /onPointerDown=\{pointerDown\}/);
  assert.match(editor, /moveGridGeometryCorner/);
  assert.match(editor, /moveGridGeometry/);
  assert.match(editor, /Cofnij punkt/);
  assert.match(editor, /Resetuj do automatu/);
  assert.match(editor, /items\.map/);
  assert.match(editor, /positionIndex \+ 1/);
  assert.match(editor, /showOverlay/);
  assert.match(editor, /zoomPercent/);
  assert.match(editor, /useState\(100\)/);
  assert.match(editor, /hasPendingIndividualDraft/);
  assert.match(editor, /showDraftReview/);
  assert.match(editor, /Kontynuuj edycję/);
  assert.match(
    editor,
    /if \(editing\) \{[\s\S]*setEditing\(false\);[\s\S]*return;/,
  );
  assert.match(
    editor,
    /onEditingChange\(isEditing \|\| hasPendingIndividualDraft\)/,
  );
  assert.match(editor, /gridGeometrySourceItemAtPoint/);
  assert.match(editor, /Kliknij siatkę na zdjęciu, aby wybrać planszę/);
  assert.match(editor, /A · Automat/);
  assert.match(editor, /B · Edycja/);
  assert.match(editor, /item\.gridColumns/);
  assert.match(editor, /item\.gridRows/);
  assert.match(editor, /previewGridReviewGeometry/);
  assert.match(editor, /saveGridReviewGeometry/);
  assert.match(editor, /Wyznacz plansze osobno/);
  assert.match(editor, /Kontynuuj plansze osobno/);
  assert.match(editor, /Wstrzymaj plansze osobno/);
  assert.match(editor, /firstIncompleteGridGeometrySourceItem/);
  assert.match(editor, /gridGeometryDraftAnchor/);
  assert.match(editor, /if \(anchor === null\)/);
  assert.match(editor, /completeGridGeometrySourceDrafts/);
  assert.match(editor, /saveGridReviewSourceGeometry/);
  assert.match(editor, /Zapisz i zatwierdź/);
  assert.doesNotMatch(editor, /setSourceDrafts\(emptyGridGeometrySourceDrafts/);
  assert.doesNotMatch(editor, /upload|overlay.*(?:jpeg|jpg)/i);
});

test('whole-image approval and source manual geometry use one explicit atomic request', () => {
  assert.match(workspace, /approveGridReviewSource\(api, sourceItems\)/);
  assert.doesNotMatch(
    workspace,
    /for \(const candidate of sourceItems\)[\s\S]{0,400}approveGridReview/,
  );
  assert.match(actions, /approveImageGridReviewSourceGeometry/);
  assert.match(actions, /createImageGridReviewSourceGeometryRevision/);
});

test('source-scoped client request is explicit and cannot spill into remote reviewer access', () => {
  assert.match(state, /GRID_REVIEW_SOURCE_PAGE_LIMIT = 9/);
  assert.match(workspace, /loadGridReviewSource/);
  assert.match(workspace, /GRID_REVIEW_SOURCE_PAGE_LIMIT/);
  assert.doesNotMatch(proxy, /sourceImageId/);
});
