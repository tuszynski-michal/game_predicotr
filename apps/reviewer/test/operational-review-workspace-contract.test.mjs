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

test('operational workspace compares square cell crops with one cropped board', async () => {
  const source = await readFile(workspacePath, 'utf8');
  const styles = await readFile(stylesPath, 'utf8');
  const reviewerStyles = await readFile(reviewerStylesPath, 'utf8');
  const actions = await readFile(actionsPath, 'utf8');
  const geometryEditor = await readFile(geometryEditorPath, 'utf8');

  assert.match(source, /loadOperationalReviewPage/);
  assert.match(actions, /limit: 1/);
  assert.match(source, /item\.cells\.map/);
  assert.match(source, /Widok planszy/);
  assert.match(source, /Plansze kompletne/);
  assert.match(source, /Wycięty układ/);
  assert.match(source, /item\.id,\s*'board'/);
  assert.doesNotMatch(source, /item\.id,\s*'source'/);
  assert.match(source, /Edycja dozwolona/);
  assert.match(source, /Brak lokalnego obrazu/);
  assert.match(actions, /IMAGE_REVIEW_CURSOR_STALE/);
  assert.match(source, /resolveOperationalReview/);
  assert.match(source, /window\.addEventListener\('keydown'/);
  assert.match(source, /event\.repeat/);
  assert.match(source, /isOperationalReviewTypingTarget/);
  assert.match(source, /operationalReviewKeyboardAction/);
  assert.match(source, /globalThis\.crypto\.randomUUID/);
  assert.match(source, /operationalReviewSuggestions/);
  assert.match(source, /operationalReviewLegend/);
  assert.match(source, /naciśnij Enter, aby od razu zapisać/);
  assert.doesNotMatch(source, /operational-review-confirm-title/);
  assert.match(actions, /IMAGE_REVIEW_REVISION_CONFLICT/);
  assert.match(source, /OperationalReviewGeometryEditor/);
  assert.match(geometryEditor, /Edytuj siatkę/);
  assert.match(geometryEditor, /onPointerMove/);
  assert.match(geometryEditor, /for \(let column = 0; column <= 5/);
  assert.match(geometryEditor, /for \(let row = 0; row <= 3/);
  assert.match(geometryEditor, /Array\.from\(\{ length: 15 \}/);
  assert.match(geometryEditor, /previewOperationalReviewGeometry/);
  assert.match(geometryEditor, /saveOperationalReviewGeometry/);
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
  assert.match(
    reviewerStyles,
    /\.operationalReviewBoardReference[\s\S]*height:\s*min\(300px,\s*28vw\)/,
  );
});
