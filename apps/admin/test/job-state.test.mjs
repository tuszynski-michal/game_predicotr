import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canCancelJob,
  canRetryJob,
  formatElapsedSeconds,
  formatImageThroughput,
  formatJobTimestamp,
  formatStorageBytes,
  isActiveJob,
  isImageImportJob,
  jobProgressLabel,
  jobProgressPercent,
  jobStageLabel,
  jobStatusLabel,
  jobTypeLabel,
  replaceJob,
} from '../src/features/jobs/job-state.ts';

function job(overrides = {}) {
  return {
    attemptCount: 1,
    cancelRequestedAt: null,
    createdAt: '2026-07-27T10:00:00Z',
    error: null,
    finishedAt: null,
    gameId: 'game-1',
    heartbeatAt: null,
    id: 'job-1',
    inputPayload: {
      schemaVersion: 1,
      datasetVersionId: 'dataset-1',
    },
    jobType: 'validate',
    leaseExpiresAt: null,
    progress: {
      current: 25,
      failed: 2,
      review: 1,
      stage: 'validating_layouts',
      succeeded: 22,
      total: 100,
    },
    startedAt: null,
    status: 'created',
    updatedAt: '2026-07-27T10:00:00Z',
    workerVersion: null,
    ...overrides,
  };
}

test('presents every lifecycle value as explicit text', () => {
  assert.equal(jobStatusLabel('created'), 'Oczekuje');
  assert.equal(jobStatusLabel('processing'), 'W toku');
  assert.equal(jobStatusLabel('waiting_for_review'), 'Wymaga review');
  assert.equal(jobStatusLabel('completed'), 'Ukończone');
  assert.equal(jobStatusLabel('failed'), 'Błąd');
  assert.equal(jobStatusLabel('cancelled'), 'Anulowane');
  assert.equal(jobTypeLabel('android_build'), 'Build APK');
  assert.equal(jobStageLabel('writing_layouts'), 'writing layouts');
  assert.equal(jobStageLabel(null), 'Etap nie został jeszcze rozpoczęty');
});

test('derives active polling, cancel and retry actions from lifecycle', () => {
  assert.equal(isActiveJob(job({ status: 'created' })), true);
  assert.equal(isActiveJob(job({ status: 'processing' })), true);
  assert.equal(isActiveJob(job({ status: 'waiting_for_review' })), false);

  assert.equal(canCancelJob(job({ status: 'created' })), true);
  assert.equal(canCancelJob(job({ status: 'processing' })), true);
  assert.equal(
    canCancelJob(
      job({
        cancelRequestedAt: '2026-07-27T10:01:00Z',
        status: 'processing',
      }),
    ),
    false,
  );
  assert.equal(canCancelJob(job({ status: 'failed' })), false);

  assert.equal(canRetryJob(job({ status: 'failed' })), true);
  assert.equal(canRetryJob(job({ status: 'waiting_for_review' })), true);
  assert.equal(canRetryJob(job({ status: 'cancelled' })), false);
});

test('formats determinate and unknown progress without hiding counts', () => {
  const determinate = job();
  assert.equal(jobProgressPercent(determinate), 25);
  assert.match(jobProgressLabel(determinate), /25\s*\/\s*100/);

  const unknown = job({
    progress: { ...determinate.progress, current: 250, total: null },
  });
  assert.equal(jobProgressPercent(unknown), null);
  assert.match(jobProgressLabel(unknown), /250/);
});

test('replaces a mutated job without reordering the server list', () => {
  const first = job();
  const second = job({ id: 'job-2', status: 'failed' });
  const updated = { ...second, status: 'created' };

  const result = replaceJob([first, second], updated);

  assert.deepEqual(
    result.map((item) => [item.id, item.status]),
    [
      ['job-1', 'created'],
      ['job-2', 'created'],
    ],
  );
  assert.equal(formatJobTimestamp(null), '—');
  assert.equal(formatJobTimestamp('not-a-date'), 'Nieprawidłowa data');
});

test('recognizes image imports and formats operational metrics', () => {
  const imageImport = job({
    inputPayload: {
      schemaVersion: 1,
      importKind: 'image_directory',
      pipelineFingerprint: 'a'.repeat(64),
    },
    jobType: 'import',
  });

  assert.equal(isImageImportJob(imageImport), true);
  assert.equal(isImageImportJob(job()), false);
  assert.equal(formatElapsedSeconds(null), 'Nie rozpoczęto');
  assert.equal(formatElapsedSeconds(42.4), '42 s');
  assert.equal(formatElapsedSeconds(125), '2 min 5 s');
  assert.equal(formatImageThroughput(null), 'Brak pomiaru');
  assert.match(formatImageThroughput(12.5), /12,5 plików\/min/);
  assert.equal(formatStorageBytes(512), '512 B');
  assert.match(formatStorageBytes(1536), /1,5 KB/);
});
