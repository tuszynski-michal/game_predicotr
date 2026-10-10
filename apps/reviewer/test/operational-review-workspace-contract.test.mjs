import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspacePath = new URL(
  '../src/features/operational-reviews/operational-review-workspace.tsx',
  import.meta.url,
);
const stylesPath = new URL('../../admin/src/app/globals.css', import.meta.url);
const reviewerStylesPath = new URL('../src/app/reviewer.css', import.meta.url);
const actionsPath = new URL(
  '../src/features/operational-reviews/operational-review-actions.ts',
  import.meta.url,
);
const geometryEditorPath = new URL(
  '../src/features/operational-reviews/operational-review-geometry-editor.tsx',
  import.meta.url,
);
const correctionTargetPath = new URL(
  '../src/features/operational-reviews/board-geometry-correction-target.ts',
  import.meta.url,
);
const deferredGeometryPath = new URL(
  '../src/features/operational-reviews/deferred-board-cell-geometry-queue.tsx',
  import.meta.url,
);
const deferredGeometryEditorPath = new URL(
  '../src/features/operational-reviews/deferred-board-cell-geometry-editor.tsx',
  import.meta.url,
);
const deferredGeometryActionsPath = new URL(
  '../src/features/operational-reviews/deferred-board-cell-geometry-actions.ts',
  import.meta.url,
);

test('operational workspace compares square cell crops with one cropped board', async () => {
  const source = await readFile(workspacePath, 'utf8');
  const styles = await readFile(stylesPath, 'utf8');
  const reviewerStyles = await readFile(reviewerStylesPath, 'utf8');
  const actions = await readFile(actionsPath, 'utf8');
  const geometryEditor = await readFile(geometryEditorPath, 'utf8');
  const correctionTarget = await readFile(correctionTargetPath, 'utf8');
  const deferredGeometry = await readFile(deferredGeometryPath, 'utf8');
  const deferredGeometryEditor = await readFile(
    deferredGeometryEditorPath,
    'utf8',
  );
  const deferredGeometryActions = await readFile(
    deferredGeometryActionsPath,
    'utf8',
  );

  assert.match(source, /loadOperationalReviewPage/);
  assert.match(actions, /limit: 1/);
  assert.match(source, /item\.cells\.map/);
  assert.match(source, /REVIEW_QUEUE_VIEW = 'all'/);
  assert.match(source, /resumeAtFirstPending: true/);
  assert.match(source, /Wszystkie/);
  assert.match(source, /Do poprawy siatki/);
  assert.match(source, /gridIssueView/);
  assert.match(source, /needsGridFixCount/);
  assert.match(actions, /gridIssueView/);
  assert.doesNotMatch(source, /onViewChange/);
  assert.match(actions, /OPERATIONAL_REVIEW_NEXT_BUFFER_LIMIT/);
  assert.match(actions, /operationalReviewPageBufferAppendNext/);
  assert.match(actions, /operationalReviewPageBufferSetPrevious/);
  assert.match(source, /prefetchOperationalReviewPageBuffer/);
  assert.match(source, /operationalReviewPageBufferAdvance/);
  assert.match(source, /operationalReviewPageBufferRetreat/);
  assert.match(source, /afterCursor: nextCursor/);
  assert.match(source, /beforeCursor: previousCursor/);
  assert.match(source, /const canAdvance =/);
  assert.match(source, /canAdvance\s*\?\s*'Dalej'/);
  assert.match(
    source,
    /aria-label="Zatwierdź lub przejdź do następnej planszy"[\s\S]*onClick=\{\(\) => void submitResolution\(\)\}/,
  );
  assert.doesNotMatch(source, /Plansza do porównania/);
  assert.doesNotMatch(source, />\s*Wycięty układ/);
  assert.match(source, /item\.geometry\.displayAssetKind === 'source_context'/);
  assert.match(source, /item\.id,\s*'board'/);
  assert.match(source, /item\.id,\s*'source'/);
  assert.match(source, /OperationalReviewNativeContext/);
  assert.match(source, /operationalReviewNativeContextViewport/);
  assert.match(source, /crossOrigin="anonymous"/);
  assert.match(source, /usage: 'native-context-v2'/);
  assert.match(source, /Edycja dozwolona/);
  assert.match(source, /Brak lokalnego obrazu/);
  assert.match(actions, /IMAGE_REVIEW_CURSOR_STALE/);
  assert.match(source, /resolveOperationalReview/);
  assert.match(source, /window\.addEventListener\('keydown'/);
  assert.match(source, /event\.repeat/);
  assert.match(source, /isOperationalReviewTypingTarget/);
  assert.match(source, /operationalReviewKeyboardAction/);
  assert.match(source, /globalThis\.crypto\.randomUUID/);
  assert.match(source, /resolutionIdempotencyKey/);
  assert.match(source, /operationalReviewPageBufferAfterResolution/);
  assert.match(source, /operationalReviewSuggestions/);
  assert.match(source, /operationalReviewLegend/);
  assert.match(source, /naciśnij Enter, aby od razu zapisać/);
  assert.doesNotMatch(source, /operational-review-confirm-title/);
  assert.match(actions, /IMAGE_REVIEW_REVISION_CONFLICT/);
  assert.match(
    source,
    /if \(result\.isRevisionConflict\) \{[\s\S]*setResolutionIdempotencyKey\(null\);[\s\S]*onReload\(\);/,
  );
  assert.match(source, /OperationalReviewGeometryEditor/);
  assert.match(geometryEditor, /Edytuj siatkę/);
  // TASK-0798: the dialog hosts the shared single-board editor of the
  // correction queue with the operational target (same flags, qualification
  // and validation), instead of its own copy of the canvas editor.
  assert.match(geometryEditor, /BoardGeometryCorrectionEditor/);
  assert.match(geometryEditor, /operationalBoardGeometryTarget/);
  assert.match(geometryEditor, /saveLabel="Zapisz nową rewizję"/);
  assert.match(geometryEditor, /Zamknij edytor i przeładuj planszę/);
  assert.doesNotMatch(geometryEditor, /Oryginał i ukośna siatka/);
  assert.doesNotMatch(geometryEditor, /onPointerMove/);
  assert.match(correctionTarget, /previewOperationalReviewGeometry/);
  assert.match(correctionTarget, /saveOperationalReviewGeometry/);
  assert.match(correctionTarget, /buildOperationalReviewGeometryCommand/);
  assert.match(correctionTarget, /correctionGeometryQualification/);
  assert.match(correctionTarget, /usage: 'board-cell-geometry-editor-v19-v1'/);
  assert.match(deferredGeometryEditor, /15 finalnych cropów source-direct/);
  assert.match(deferredGeometryEditor, /backgroundSize: '500% 300%'/);
  assert.match(deferredGeometryEditor, /poza zdjęciem/);
  assert.match(source, /onGeometrySaved=\{handleGeometrySaved\}/);
  assert.match(source, /Plansza wróciła do weryfikacji symboli/);
  assert.match(source, /DeferredBoardCellGeometryQueue/);
  assert.match(source, /deferredGeometryOpen/);
  assert.match(deferredGeometry, /Otwórz korektę siatki/);
  assert.match(deferredGeometry, /Pomiń na razie/);
  assert.match(deferredGeometryActions, /status: 'pending'/);
  assert.match(deferredGeometryActions, /limit: 1/);
  assert.match(deferredGeometryEditor, /operationalReviewPointInLattice/);
  assert.match(deferredGeometryEditor, /for \(let column = 0; column <= 5/);
  assert.match(deferredGeometryEditor, /for \(let row = 0; row <= 3/);
  assert.match(deferredGeometryEditor, /Array\.from\(\{ length: 15 \}/);
  assert.match(deferredGeometryEditor, /previewIsCurrent/);
  assert.match(deferredGeometryEditor, /idempotencyRef/);
  assert.match(
    deferredGeometryEditor,
    /operationalReviewTranslatedGeometryCorners/,
  );
  assert.match(
    deferredGeometryEditor,
    /operationalReviewGeometryContainsPoint/,
  );
  assert.match(deferredGeometryEditor, /translateGridRef/);
  assert.match(deferredGeometryEditor, /Wycentruj widok na siatce/);
  assert.doesNotMatch(deferredGeometryEditor, /Aktywne przesuwanie/);
  // The JSX text wraps across lines, so the words are separated by any whitespace.
  assert.match(deferredGeometryEditor, /obraz pozostaje\s+statyczny/i);
  assert.match(deferredGeometryEditor, /przesunąć cały obrys/i);
  assert.match(
    deferredGeometryEditor,
    /\{\s*recenterViewport = false,\s*\}: \{ readonly recenterViewport\?: boolean \} = \{\}/,
  );
  assert.match(deferredGeometryEditor, /replaceCorners\(next\);/);
  assert.match(
    deferredGeometryEditor,
    // TASK-0882: resetting a stored board lattice restores the corners of the
    // lattice boundary, and only a board without one the suggested corners.
    /replaceCorners\(\s*original === null\s*\?\s*copyCorners\(context\.suggestedCorners\)\s*:\s*boardLatticeCorners\(original\),\s*\{\s*recenterViewport: true,/,
  );
  assert.match(deferredGeometryEditor, /onPointerDown=\{startCanvasGesture\}/);
  assert.match(deferredGeometryEditor, /Zapisz geometrię i dalej/);
  assert.match(deferredGeometry, /onOrdinaryQueueChanged/);
  assert.match(reviewerStyles, /\.deferredGeometryQueue\s*\{/);
  assert.match(source, /version: cell\.cropChecksumSha256/);
  assert.match(source, /version: item\.sourceChecksumSha256/);
  assert.match(source, /Zamroź kohortę/);
  assert.match(source, /Nie uruchomi treningu ani/);
  assert.match(actions, /freezeVerifiedImageReviewCohort/);
  assert.match(actions, /listVerifiedImageReviewCohorts/);
  assert.ok(
    source.indexOf('className="operationalReviewGrid"') <
      source.indexOf('className="operationalReviewBoardReference"'),
  );

  assert.match(
    styles,
    /\.operationalReviewGrid\s*\{[\s\S]*grid-template-columns:\s*repeat\(5,/,
  );
  assert.match(
    reviewerStyles,
    /\.operationalReviewVisualComparison\s*\{[\s\S]*grid-template-columns:\s*minmax\(390px,\s*480px\)\s*minmax\(320px,\s*1fr\)/,
  );
  assert.match(
    reviewerStyles,
    /\.operationalReviewCell\s*\{[\s\S]*aspect-ratio:\s*1/,
  );
  assert.match(reviewerStyles, /\.operationalReviewNativeContext\s*\{/);
  assert.match(reviewerStyles, /overflow:\s*hidden/);
  assert.match(
    reviewerStyles,
    /\.operationalReviewApprove:disabled\s*\{[\s\S]*cursor:\s*not-allowed/,
  );
});

test('the operational screen offers the guarded board rejection (TASK-0970)', async () => {
  const source = await readFile(workspacePath, 'utf8');

  // One button with a reason picker and a confirmation, sent through the
  // existing resolution route; a result goes through the normal resolve path.
  assert.match(source, /<RejectBoardControl/);
  assert.match(source, /rejectReviewItem\(/);
  assert.match(source, /onDone=\{onResolved\}/);
  assert.match(source, /BOARD_REJECT_CANONICAL|Kanonicznego właściciela/);
  // Symbol shortcuts stay silent while a modal `div` (not only `dialog`) is open.
  assert.match(source, /\[aria-modal="true"\]/);
  // A rejected or superseded board has nothing to reject.
  assert.match(
    source,
    /item\.status === 'rejected'\s*\|\|\s*item\.status === 'superseded'/,
  );
});
