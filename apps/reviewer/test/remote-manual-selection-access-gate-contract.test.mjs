import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const gatePath = new URL(
  '../src/features/manual-selection/remote-manual-selection-access-gate.tsx',
  import.meta.url,
);
const pagePath = new URL(
  '../src/app/manual-selection/page.tsx',
  import.meta.url,
);
const legacyProxyPath = new URL(
  '../src/app/review-api/[...path]/route.ts',
  import.meta.url,
);
const workspacePath = new URL(
  '../src/features/manual-selection/remote-manual-selection-workspace-foundation.tsx',
  import.meta.url,
);
const remoteStorePath = new URL(
  '../src/features/manual-selection/remote-selection-store.ts',
  import.meta.url,
);

test('manual selection shell uses only purpose-scoped same-origin endpoints', async () => {
  const gate = await readFile(gatePath, 'utf8');
  const page = await readFile(pagePath, 'utf8');

  assert.match(gate, /\/selection-api\/api\/v1\/remote-manual-selections/);
  assert.match(gate, /clientInstanceId/);
  assert.match(gate, /writer-lease\/\$\{action\}/);
  assert.match(gate, /'heartbeat'/);
  assert.match(gate, /'takeover'/);
  assert.doesNotMatch(gate, /gameId|importJobId|\/review-api/);
  assert.match(page, /isRemoteManualSelectionEnabled/);
  assert.doesNotMatch(page, /mode=local|isLoopbackReviewerHost/);
});

test('manual selection shell does not persist access code or bearer token', async () => {
  const gate = await readFile(gatePath, 'utf8');

  assert.match(gate, /sessionStorage\.setItem\(CLIENT_INSTANCE_KEY/);
  assert.doesNotMatch(gate, /localStorage/);
  assert.doesNotMatch(gate, /setItem\([^\n]*(?:accessCode|token)/i);
  assert.doesNotMatch(gate, /accessToken/);
});

test('remote selection cookie cannot authorize the legacy Reviewer proxy', async () => {
  const legacyProxy = await readFile(legacyProxyPath, 'utf8');

  assert.match(legacyProxy, /gp_reviewer_token/);
  assert.doesNotMatch(legacyProxy, /gp_remote_selection_token/);
});

test('TASK 8 workspace remains metadata-only and does not apply operations over HTTP', async () => {
  const gate = await readFile(gatePath, 'utf8');
  const workspace = await readFile(workspacePath, 'utf8');
  const store = await readFile(remoteStorePath, 'utf8');

  assert.match(gate, /RemoteManualSelectionWorkspaceFoundation/);
  assert.match(workspace, /obrazy nie są kopiowane do IndexedDB/);
  assert.match(workspace, /nie wysyła operacji ani danych JPEG do hosta/);
  assert.doesNotMatch(workspace, /\bfetch\s*\(/);
  assert.match(store, /game-predictor-remote-manual-selection/);
  assert.doesNotMatch(store, /game-predictor-manual-image-selection/);
  assert.doesNotMatch(store, /readonly (?:blob|bytes|jpegData):/i);
});
