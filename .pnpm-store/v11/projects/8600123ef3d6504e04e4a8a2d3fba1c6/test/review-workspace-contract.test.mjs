import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const workspacePath = new URL(
  '../src/features/reviews/review-workspace.tsx',
  import.meta.url,
);
const decisionPath = new URL(
  '../src/features/reviews/review-decision-panel.tsx',
  import.meta.url,
);

test('manual review workspace delegates explicit decisions to the audited panel', async () => {
  const source = await readFile(workspacePath, 'utf8');
  const decision = await readFile(decisionPath, 'utf8');

  assert.match(source, /item\.snapshot\.cells\.map/);
  assert.match(source, /ReviewDecisionPanel/);
  assert.match(source, /ReviewFeedbackExportsPanel/);
  assert.match(decision, /geometryAccepted/);
  assert.match(decision, /expectedRevision/);
  assert.match(decision, /crypto\.randomUUID/);
  assert.match(decision, /'accepted'/);
  assert.match(decision, /'corrected'/);
  assert.match(decision, /'rejected'/);
  assert.doesNotMatch(decision, /setInterval|autoAccept|autoReject/);
});
