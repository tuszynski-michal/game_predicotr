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
const operationalWorkspacePath = new URL(
  '../src/features/manual-selection/remote-manual-selection-workspace.tsx',
  import.meta.url,
);
const workspaceModelPath = new URL(
  '../src/features/manual-selection/remote-selection-workspace-model.ts',
  import.meta.url,
);
const clientRuntimePath = new URL(
  '../src/features/manual-selection/remote-selection-client-runtime.ts',
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
  const clientRuntime = await readFile(clientRuntimePath, 'utf8');

  assert.match(gate, /readOrCreateRemoteSelectionClientInstance/);
  assert.match(clientRuntime, /storage\.setItem\(key, clientInstanceId\)/);
  assert.match(clientRuntime, /catch \{/);
  assert.doesNotMatch(gate, /localStorage/);
  assert.doesNotMatch(gate, /setItem\([^\n]*(?:accessCode|token)/i);
  assert.doesNotMatch(gate, /accessToken/);
});

test('mobile access gate bounds network waits and tolerates unavailable storage', async () => {
  const gate = await readFile(gatePath, 'utf8');
  const clientRuntime = await readFile(clientRuntimePath, 'utf8');

  assert.match(gate, /fetchRemoteSelectionWithTimeout/);
  assert.match(
    gate,
    /useState\(\(\) =>\s*typeof window === 'undefined' \? '' : readClientInstance\(\)/,
  );
  assert.doesNotMatch(gate, /useSyncExternalStore/);
  assert.match(clientRuntime, /REMOTE_SELECTION_REQUEST_TIMEOUT_MS = 12_000/);
  assert.match(clientRuntime, /controller\.abort\(\)/);
  assert.match(clientRuntime, /Mobile privacy modes may expose sessionStorage/);
});

test('writer heartbeat survives workspace rerenders and recovers an expired lease', async () => {
  const gate = await readFile(gatePath, 'utf8');

  assert.match(gate, /const heartbeatLease = useCallback/);
  assert.match(
    gate,
    /\[clientInstanceId, hasContext, heartbeatLease, isWriter, loadContext\]/,
  );
  assert.match(
    gate,
    /response\.status === 401 \|\| response\.status === 409[\s\S]*await loadContext\(true\)/,
  );
});

test('remote selection cookie cannot authorize the legacy Reviewer proxy', async () => {
  const legacyProxy = await readFile(legacyProxyPath, 'utf8');

  assert.match(legacyProxy, /gp_reviewer_token/);
  assert.doesNotMatch(legacyProxy, /gp_remote_selection_token/);
});

test('operator-local workspace keeps previews, decisions and JPEG outputs on the operator device', async () => {
  const gate = await readFile(gatePath, 'utf8');
  const workspace = await readFile(workspacePath, 'utf8');
  const operationalWorkspace = await readFile(operationalWorkspacePath, 'utf8');
  const workspaceModel = await readFile(workspaceModelPath, 'utf8');
  const store = await readFile(remoteStorePath, 'utf8');

  assert.match(gate, /RemoteManualSelectionWorkspaceFoundation/);
  assert.match(
    workspace,
    /Podglądy, pozycja, zoom, decyzje i wybrane JPEG-i pozostają na tym/,
  );
  assert.match(workspace, /RemoteManualSelectionWorkspace/);
  assert.match(
    workspace,
    /REMOTE_OUTPUT_PARENT_PICKER_ID = 'gp-rms-output-parent'/,
  );
  assert.match(workspace, /const outputName = `\$\{sourceName\} wybrane`/);
  assert.match(
    workspace,
    /parent\.getDirectoryHandle\(outputName,\s*\{\s*create: true/,
  );
  assert.match(workspace, /outputDirectoryName: outputName/);
  assert.doesNotMatch(workspace, /\bfetch\s*\(/);
  assert.match(operationalWorkspace, /URL\.createObjectURL/);
  assert.match(operationalWorkspace, /URL\.revokeObjectURL/);
  assert.match(operationalWorkspace, /PREVIEW_RADIUS = 3/);
  assert.match(workspaceModel, /selected_local/);
  assert.match(operationalWorkspace, /writeOperatorLocalSelection/);
  assert.match(operationalWorkspace, /appendLocalWorkspaceDecision/);
  assert.match(operationalWorkspace, /writeOperatorLocalManifest/);
  assert.match(operationalWorkspace, /removeOperatorLocalSelection/);
  assert.match(operationalWorkspace, /Tryb lokalny operatora/);
  assert.doesNotMatch(
    operationalWorkspace,
    /Zakończ partię i zapisz manifesty/,
  );
  assert.doesNotMatch(operationalWorkspace, /hostPath|basePath|C:\\\\/);
  assert.match(store, /game-predictor-remote-manual-selection/);
  assert.doesNotMatch(store, /game-predictor-manual-image-selection/);
  assert.doesNotMatch(store, /readonly (?:blob|bytes|jpegData):/i);
});

test('operator-local decisions are serialized without host finalization or transfer', async () => {
  const operationalWorkspace = await readFile(operationalWorkspacePath, 'utf8');

  assert.match(
    operationalWorkspace,
    /interactionQueue[\s\S]*\.enqueue\(\(\) =>[\s\S]*acceptRequestedImage/,
  );
  assert.doesNotMatch(operationalWorkspace, /controlTransport/);
  assert.doesNotMatch(operationalWorkspace, /transferScheduler/);
  assert.doesNotMatch(operationalWorkspace, /countPendingOperations/);
  assert.doesNotMatch(operationalWorkspace, /syncNow/);
});

test('operator-local restart persists the parent handle and missing directories require a clean relink', async () => {
  const workspace = await readFile(workspacePath, 'utf8');
  const operationalWorkspace = await readFile(operationalWorkspacePath, 'utf8');
  const store = await readFile(remoteStorePath, 'utf8');

  assert.match(workspace, /outputParentHandle: parent/);
  assert.match(
    workspace,
    /getDirectoryHandle\([\s\S]*\{\s*create:\s*true[\s\S]*\}/,
  );
  assert.match(workspace, /restartRemoteSelectionLocalBatch/);
  assert.match(workspace, /resetOperatorLocalOutputDirectory/);
  assert.match(
    workspace,
    /remoteSelectionWorkspaceActions[\s\S]*className="primaryButton"[\s\S]*Ekran startowy[\s\S]*className="secondaryButton"[\s\S]*Restart selekcji/,
  );
  assert.match(workspace, /showStartScreen/);
  assert.match(workspace, /startScreenSourceSelected/);
  assert.match(workspace, /startScreenOutputSelected/);
  assert.match(workspace, /startScreenOutputParent/);
  assert.match(workspace, /showStartScreen && !startScreenSourceSelected/);
  assert.match(workspace, /showStartScreen && !startScreenOutputSelected/);
  assert.match(workspace, /findBatchBySourceManifest/);
  assert.match(workspace, /REMOTE_SELECTION_OUTPUT_RESUME_REQUIRED/);
  assert.doesNotMatch(workspace, /Wróć do selekcji/);
  assert.match(workspace, /Wybierz ponownie katalog zdjęć i katalog do zapisu/);
  assert.match(workspace, /remoteSelectionWorkspaceActions/);
  assert.match(workspace, /remoteSelectionResetDialogBackdrop/);
  assert.match(workspace, /Usuń wybory i zacznij od początku/);
  assert.doesNotMatch(workspace, /window\.confirm/);
  assert.match(workspace, /interactionPaused=\{resetDialogOpen\}/);
  assert.match(operationalWorkspace, /interactionPaused/);
  assert.match(workspace, /Wybierz katalog ze zdjęciami/);
  assert.match(workspace, /Wybierz katalog do zapisu/);
  assert.match(workspace, /connectOutputParent/);
  assert.match(workspace, /activeBatchId: null/);
  assert.match(workspace, /clearRemoteManualSelectionScroll/);
  assert.match(workspace, /writeBatchManifest\(/);
  assert.match(workspace, /resetLocalWorkspaceForDirectoryRelink/);
  assert.match(workspace, /Wybierz ponownie katalog ze zdjęciami/);
  assert.match(workspace, /sourceReader === null/);
  assert.match(workspace, /onStorageUnavailable/);
  assert.match(operationalWorkspace, /onStorageUnavailable/);
  assert.match(operationalWorkspace, /reportLocalError/);
  assert.match(store, /outputParentHandle: null/);
  assert.match(store, /sourceHandle: null/);
  assert.match(
    operationalWorkspace,
    /export function clearRemoteManualSelectionScroll/,
  );
});
