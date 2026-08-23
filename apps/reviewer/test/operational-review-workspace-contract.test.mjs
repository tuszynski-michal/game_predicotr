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
  assert.match(source, /Wszystkie plansze/);
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
  assert.match(geometryEditor, /Pojedynczy layout z marginesem/);
  assert.doesNotMatch(geometryEditor, /Oryginał i ukośna siatka/);
  assert.match(geometryEditor, /operationalReviewGeometryViewport/);
  assert.match(geometryEditor, /viewport\.x/);
  assert.match(geometryEditor, /operationalReviewPointInSourceImage/);
  assert.match(geometryEditor, /operationalReviewPointInCanvas/);
  assert.match(geometryEditor, /onPointerMove/);
  assert.match(geometryEditor, /onPointerUp=\{finishDragging\}/);
  assert.match(geometryEditor, /for \(let column = 0; column <= 5/);
  assert.match(geometryEditor, /for \(let row = 0; row <= 3/);
  assert.match(geometryEditor, /operationalReviewPointInLattice/);
  assert.match(geometryEditor, /operationalReviewGeometryEdgeHandles/);
  assert.match(geometryEditor, /Array\.from\(\{ length: 15 \}/);
  assert.match(geometryEditor, /previewOperationalReviewGeometry/);
  assert.match(geometryEditor, /saveOperationalReviewGeometry/);
  assert.match(geometryEditor, /buildOperationalReviewGeometryCommand/);
  assert.match(geometryEditor, /!previewIsCurrent \|\| saving/);
  assert.match(geometryEditor, /usage: 'board-cell-geometry-editor-v19-v1'/);
  assert.match(geometryEditor, /15 finalnych cropów source-direct/);
  assert.match(geometryEditor, /backgroundSize: '500% 300%'/);
  assert.match(geometryEditor, /Zapisz nową rewizję/);
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
