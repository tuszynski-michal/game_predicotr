import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import {
  createRemoteManualSelectionAccess,
  loadRemoteManualSelectionRecoveryStatus,
  loadRemoteManualSelectionMonitor,
  loadRemoteManualSelectionSessions,
  reopenRemoteManualSelectionBatch,
  revokeRemoteManualSelectionAccess,
} from '../src/features/manual-image-selection/remote-manual-selection-actions.ts';
import {
  REMOTE_SESSION_LIST_LIMIT,
  REMOTE_SESSION_FETCH_LIMIT,
  REMOTE_SESSION_LIST_POLL_MS,
  REMOTE_SESSION_MONITOR_POLL_MS,
  activeRemoteManualSelectionSessions,
  filteredRemoteManualSelectionSessions,
  newestRemoteManualSelectionSessions,
  safeRemoteManualSelectionUrl,
  selectVisibleRemoteManualSelectionSessionId,
  selectRemoteManualSelectionSessionId,
} from '../src/features/manual-image-selection/remote-manual-selection-state.ts';

const panelSource = await readFile(
  new URL(
    '../src/features/manual-image-selection/remote-manual-selection-host-panel.tsx',
    import.meta.url,
  ),
  'utf8',
);

const session = (overrides = {}) => ({
  createdAt: '2026-08-24T10:00:00Z',
  displayName: 'Operator 1',
  expiresAt: '2026-08-24T18:00:00Z',
  lockedAt: null,
  ready: true,
  revision: 0,
  reviewUrl:
    'https://safe-name.trycloudflare.com/manual-selection?session=11111111-1111-4111-8111-111111111111',
  revokedAt: null,
  sessionId: '11111111-1111-4111-8111-111111111111',
  status: 'active',
  updatedAt: '2026-08-24T10:00:00Z',
  writerActive: false,
  writerLeaseExpiresAt: null,
  ...overrides,
});

test('host actions execute the typed lifecycle without persisting a secret', async () => {
  const calls = [];
  const current = session();
  const client = {
    createRemoteManualSelectionSession: async (body) => {
      calls.push(['create', body]);
      return { data: { accessCode: 'ABCD-EFGH', session: current } };
    },
    listRemoteManualSelectionSessions: async (limit) => {
      calls.push(['list', limit]);
      return { data: { sessions: [current] } };
    },
    getRemoteManualSelectionSession: async (sessionId, limit) => {
      calls.push(['monitor', sessionId, limit]);
      return {
        data: {
          batches: [],
          diskErrorCode: null,
          diskFreeBytes: 1000,
          diskTotalBytes: 2000,
          hasMoreBatches: false,
          session: current,
        },
      };
    },
    getRemoteManualSelectionRecoveryStatus: async (sessionId, batchId) => {
      calls.push(['recovery', sessionId, batchId]);
      return {
        data: {
          batchId,
          queue: {
            pendingOperationCount: 0,
            uploadingTransferCount: 1,
            pendingTransferBytes: 100,
            materializingActionCount: 0,
            pendingHostActionCount: 0,
            syncedFileCount: 0,
            conflictFileCount: 0,
            recoveryFindings: [],
          },
          gcPreview: {
            deletionEnabled: false,
            scannedArtifactCount: 1,
            scannedBytes: 100,
            categories: [],
            findings: [],
          },
        },
      };
    },
    revokeRemoteManualSelectionSession: async (sessionId) => {
      calls.push(['revoke', sessionId]);
      return { data: { ...current, status: 'revoked' } };
    },
    reopenRemoteManualSelectionBatch: async (sessionId, body) => {
      calls.push(['reopen', sessionId, body]);
      return {
        data: {
          batch: { batchId: body.batchId, status: 'active' },
          reopenedAt: '2026-08-24T12:00:00Z',
        },
      };
    },
  };

  assert.equal(
    (
      await createRemoteManualSelectionAccess(client, {
        label: '  Operator 1  ',
        lifetimeMinutes: 480,
      })
    ).data.accessCode,
    'ABCD-EFGH',
  );
  assert.equal((await loadRemoteManualSelectionSessions(client)).ok, true);
  assert.equal(
    (await loadRemoteManualSelectionMonitor(client, current.sessionId)).ok,
    true,
  );
  assert.equal(
    (
      await loadRemoteManualSelectionRecoveryStatus(
        client,
        current.sessionId,
        '22222222-2222-4222-8222-222222222222',
      )
    ).data.queue.pendingTransferBytes,
    100,
  );
  assert.equal(
    (await revokeRemoteManualSelectionAccess(client, current.sessionId)).ok,
    true,
  );
  assert.equal(
    (
      await reopenRemoteManualSelectionBatch(client, {
        batchId: '22222222-2222-4222-8222-222222222222',
        expectedFinalManifestChecksumSha256: 'a'.repeat(64),
        expectedServerRevision: 4,
        sessionId: current.sessionId,
      })
    ).ok,
    true,
  );
  assert.deepEqual(calls, [
    [
      'create',
      {
        label: 'Operator 1',
        lifetimeMinutes: 480,
      },
    ],
    ['list', 100],
    ['monitor', current.sessionId, 100],
    ['recovery', current.sessionId, '22222222-2222-4222-8222-222222222222'],
    ['revoke', current.sessionId],
    [
      'reopen',
      current.sessionId,
      {
        batchId: '22222222-2222-4222-8222-222222222222',
        expectedFinalManifestChecksumSha256: 'a'.repeat(64),
        expectedServerRevision: 4,
      },
    ],
  ]);
});

test('selects active sessions and accepts only exact safe tunnel URLs', () => {
  const active = session();
  const revoked = session({
    sessionId: '22222222-2222-4222-8222-222222222222',
    status: 'revoked',
  });
  assert.deepEqual(activeRemoteManualSelectionSessions([revoked, active]), [
    active,
  ]);
  assert.equal(
    selectRemoteManualSelectionSessionId([revoked, active], ''),
    active.sessionId,
  );
  assert.match(safeRemoteManualSelectionUrl(active), /trycloudflare\.com/);
  assert.equal(
    safeRemoteManualSelectionUrl({
      ...active,
      reviewUrl: `https://evil.example/manual-selection?session=${active.sessionId}`,
    }),
    null,
  );
  assert.equal(
    safeRemoteManualSelectionUrl({
      ...active,
      reviewUrl:
        'https://safe-name.trycloudflare.com/manual-selection?session=foreign',
    }),
    null,
  );
});

test('keeps only the ten newest sessions in deterministic order', () => {
  const sessions = Array.from({ length: 12 }, (_, index) =>
    session({
      createdAt: `2026-08-${String(index + 1).padStart(2, '0')}T10:00:00Z`,
      sessionId: `00000000-0000-4000-8000-${String(index + 1).padStart(12, '0')}`,
    }),
  );

  assert.equal(REMOTE_SESSION_LIST_LIMIT, 10);
  assert.deepEqual(
    newestRemoteManualSelectionSessions(sessions).map(
      (entry) => entry.createdAt,
    ),
    sessions
      .slice(2)
      .reverse()
      .map((entry) => entry.createdAt),
  );
});

test('filters the ten newest active or completed sessions without hiding drafts', () => {
  const draft = session({
    createdAt: '2026-08-24T12:00:00Z',
    sessionId: '00000000-0000-4000-8000-000000000001',
    status: 'draft',
  });
  const active = session({
    createdAt: '2026-08-24T11:00:00Z',
    sessionId: '00000000-0000-4000-8000-000000000002',
  });
  const completed = session({
    createdAt: '2026-08-24T10:00:00Z',
    sessionId: '00000000-0000-4000-8000-000000000003',
    status: 'completed',
  });
  const expired = session({
    createdAt: '2026-08-24T09:00:00Z',
    sessionId: '00000000-0000-4000-8000-000000000004',
    status: 'expired',
  });
  const revoked = session({
    createdAt: '2026-08-24T08:00:00Z',
    sessionId: '00000000-0000-4000-8000-000000000005',
    status: 'revoked',
  });

  assert.equal(REMOTE_SESSION_FETCH_LIMIT, 100);
  assert.deepEqual(
    filteredRemoteManualSelectionSessions(
      [revoked, expired, completed, active, draft],
      'active',
    ).map((entry) => entry.status),
    ['draft', 'active'],
  );
  const ended = filteredRemoteManualSelectionSessions(
    [revoked, expired, completed, active, draft],
    'completed',
  );
  assert.deepEqual(
    ended.map((entry) => entry.status),
    ['completed', 'expired', 'revoked'],
  );
  assert.equal(
    selectVisibleRemoteManualSelectionSessionId(ended, active.sessionId),
    completed.sessionId,
  );
});

test('panel keeps secret in React memory and uses bounded polling and exact revoke', () => {
  assert.equal(REMOTE_SESSION_LIST_POLL_MS, 30_000);
  assert.equal(REMOTE_SESSION_MONITOR_POLL_MS, 10_000);
  assert.match(panelSource, /Najnowsze sesje/);
  assert.match(panelSource, /Filtr najnowszych sesji/);
  assert.match(panelSource, /Aktywne/);
  assert.match(panelSource, /Zakończone/);
  assert.match(
    panelSource,
    /useState<RemoteManualSelectionSessionCreatedResponse/,
  );
  assert.doesNotMatch(panelSource, /localStorage|sessionStorage|indexedDB/i);
  assert.match(
    panelSource,
    /loadRemoteManualSelectionMonitor\(api, sessionId\)/,
  );
  assert.match(panelSource, /revokeSession\(selectedSession\.sessionId\)/);
  assert.match(panelSource, /Inne sesje i wspólny tunel nie zostały przerwane/);
  assert.match(panelSource, /Kod jednorazowy — nie pojawi się po odświeżeniu/);
  assert.doesNotMatch(panelSource, /Wybierz folder bazowy/);
  assert.match(panelSource, /wybrane obrazy pozostają wyłącznie na urządzeniu/);
  assert.match(
    panelSource,
    /Twój komputer przechowuje tylko kod i czas dostępu/,
  );
  assert.match(panelSource, /Etykieta sesji/);
  assert.doesNotMatch(panelSource, /Partie \(maksymalnie 100\)/);
  assert.doesNotMatch(panelSource, /Operator nie utworzył jeszcze partii/);
  assert.doesNotMatch(panelSource, /remoteManualSelectionBatches/);
  assert.doesNotMatch(panelSource, /reopenRemoteManualSelectionBatch/);
  assert.doesNotMatch(panelSource, /loadRemoteManualSelectionRecoveryStatus/);
});
