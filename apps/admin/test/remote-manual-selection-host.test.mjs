import assert from 'node:assert/strict';
import test from 'node:test';
import { readFile } from 'node:fs/promises';

import {
  createRemoteManualSelectionAccess,
  loadRemoteManualSelectionMonitor,
  loadRemoteManualSelectionSessions,
  reopenRemoteManualSelectionBatch,
  revokeRemoteManualSelectionAccess,
  selectRemoteManualSelectionBase,
} from '../src/features/manual-image-selection/remote-manual-selection-actions.ts';
import {
  REMOTE_SESSION_LIST_POLL_MS,
  REMOTE_SESSION_MONITOR_POLL_MS,
  activeRemoteManualSelectionSessions,
  safeRemoteManualSelectionUrl,
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
    selectRemoteManualSelectionHostBase: async () => {
      calls.push(['select']);
      return {
        data: {
          baseCapability: 'x'.repeat(32),
          displayName: 'Documents',
          expiresAt: '2026-08-24T10:05:00Z',
          status: 'selected',
        },
      };
    },
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

  assert.equal((await selectRemoteManualSelectionBase(client)).ok, true);
  assert.equal(
    (
      await createRemoteManualSelectionAccess(client, {
        baseCapability: 'x'.repeat(32),
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
    ['select'],
    [
      'create',
      {
        baseCapability: 'x'.repeat(32),
        label: 'Operator 1',
        lifetimeMinutes: 480,
      },
    ],
    ['list', 100],
    ['monitor', current.sessionId, 100],
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

test('panel keeps secret in React memory and uses bounded polling and exact revoke', () => {
  assert.equal(REMOTE_SESSION_LIST_POLL_MS, 30_000);
  assert.equal(REMOTE_SESSION_MONITOR_POLL_MS, 10_000);
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
  assert.match(panelSource, /Wybierz folder bazowy/);
  assert.match(panelSource, /Etykieta sesji/);
  assert.match(panelSource, /expectedFinalManifestChecksumSha256/);
  assert.match(panelSource, /Potwierdź ponowne otwarcie/);
});
