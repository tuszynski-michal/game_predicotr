import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

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

test('the reviewer owns the dark application foundation and styled controls', () => {
  assert.match(reviewerCss, /:root\s*\{[\s\S]*--background:\s*#07101d/);
  assert.match(reviewerCss, /color-scheme:\s*dark/);
  assert.match(reviewerCss, /button\s*\{[\s\S]*appearance:\s*none/);
  assert.match(reviewerCss, /\.deferredGeometryQueue\s*\{/);
});

test('the local reviewer is only the correction screen; remote stays restricted', () => {
  assert.match(gate, /gridValidationEnabled[\s\S]*LocalReviewerWorkspace/);
  assert.match(gate, /OperationalReviewWorkspace/);
  // D-462: the local Reviewer is only the single correction screen.
  assert.match(localWorkspace, /BoardGeometryCorrectionWorkspace/);
  assert.doesNotMatch(
    localWorkspace,
    /GridReviewWorkspace|OperationalReviewWorkspace|Walidacja gotowych siatek|Niepełne siatki/,
  );
  assert.match(page, /gridValidationEnabled=\{localMode\}/);
  assert.doesNotMatch(page, /REVIEWER_GRID_VALIDATION/);
  assert.doesNotMatch(proxy, /\/grid-reviews/);
  assert.doesNotMatch(proxy, /\/image-reviews\//);
});

test('the local reviewer has the correction and gaps tabs over one mounted editor (TASK-0962)', () => {
  assert.match(localWorkspace, /Do korekty/);
  assert.match(localWorkspace, /Braki zdjęć/);
  assert.match(localWorkspace, /Lista braków pojawi się w kolejnym kroku/);
  // Both panels stay mounted; the inactive one is only hidden.
  assert.match(localWorkspace, /hidden=\{tab !== 'correction'\}/);
  assert.match(localWorkspace, /keyboardEnabled=\{tab === 'correction'\}/);
});

test('the grid-audit list is a loopback-only local mode without a proxy route (TASK-0840)', () => {
  // Same loopback gate as the local correction screen; scoped by game only.
  assert.match(
    page,
    /loopbackLocal =\s*value\(params\.mode\) === 'local' &&\s*isLoopbackReviewerHost/,
  );
  assert.match(
    page,
    /gridAuditMode = loopbackLocal && value\(params\.queue\) === 'grid-audit'/,
  );
  assert.match(page, /gridAuditScope=\{gridAuditMode \? \{ gameId \} : null\}/);
  // TASK-0805 added the loopback-only grid shadow mode to the same API base
  // URL choice, so the local branch now lists all three local modes.
  assert.match(
    page,
    /localMode \|\| gridAuditMode \|\| gridShadowMode\s*\?\s*resolveLocalAdminApiBaseUrl/,
  );
  assert.match(
    gate,
    /gridAuditScope !== null[\s\S]*GridAuditCorrectionWorkspace/,
  );
  assert.doesNotMatch(proxy, /grid-audit/);
});

test('the whole-photo grid validation and its mode switch are gone', () => {
  // TASK-0727: no module may bring back board or photo approval.
  for (const removed of [
    '../src/features/grid-reviews',
    '../src/features/access/local-reviewer-workspace-state.ts',
  ]) {
    assert.equal(existsSync(new URL(removed, import.meta.url)), false, removed);
  }
  assert.doesNotMatch(reviewerCss, /\.gridReview|\.localReviewerMode/);
});
