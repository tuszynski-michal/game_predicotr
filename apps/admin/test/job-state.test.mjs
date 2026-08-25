import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canCancelJob,
  canDeleteImageSelectionJob,
  canRetryJob,
  formatElapsedSeconds,
  formatImageThroughput,
  formatJobTimestamp,
  formatStorageBytes,
  imageImportAutomationTiming,
  isActiveJob,
  isImageImportJob,
  jobContextLabel,
  jobSourceRangeLabel,
  jobErrorSummary,
  jobProgressLabel,
  jobProgressPercent,
  jobProgressPresentation,
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
  assert.equal(jobTypeLabel('image_selection'), 'Selekcja zdjęć');
  assert.equal(jobStageLabel('writing_layouts'), 'writing layouts');
  assert.equal(jobStageLabel(null), 'Etap nie został jeszcze rozpoczęty');
});

test('labels image import and geometry preflight jobs with their source range', () => {
  const importJob = job({
    inputPayload: {
      schemaVersion: 5,
      importKind: 'image_directory',
      sourceDisplayName: '19810 - 45162',
    },
    jobType: 'import',
  });
  const geometryPreflight = job({
    inputPayload: {
      schemaVersion: 2,
      sourceDisplayName: '45163 - 70731 v20',
      validationKind: 'page_geometry_preflight',
    },
    jobType: 'validate',
  });

  assert.equal(jobSourceRangeLabel(importJob), 'Zakres 19810–45162');
  assert.equal(jobSourceRangeLabel(geometryPreflight), 'Zakres 45163–70731');
  assert.equal(
    jobSourceRangeLabel(
      job({
        inputPayload: {
          schemaVersion: 2,
          sourceDirectory: 'C:\\managed\\70363 - 93861',
          validationKind: 'page_geometry_preflight',
        },
        jobType: 'validate',
      }),
    ),
    'Zakres 70363–93861',
  );
  assert.equal(jobSourceRangeLabel(job()), null);
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
  assert.equal(
    canDeleteImageSelectionJob(
      job({ jobType: 'image_selection', status: 'cancelled' }),
    ),
    true,
  );
  assert.equal(
    canDeleteImageSelectionJob(
      job({ jobType: 'image_selection', status: 'processing' }),
    ),
    false,
  );
  assert.equal(canDeleteImageSelectionJob(job({ status: 'cancelled' })), false);
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

test('presents two-phase image imports as real image counts', () => {
  const imageImport = job({
    inputPayload: {
      schemaVersion: 1,
      importKind: 'image_directory',
      pipelineFingerprint: 'a'.repeat(64),
    },
    jobType: 'import',
    progress: {
      current: 1021,
      failed: 106,
      review: 176,
      stage: 'image_pipeline:sequence_ocr',
      succeeded: 739,
      total: 1478,
    },
  });

  assert.deepEqual(jobProgressPresentation(imageImport), {
    current: 282,
    total: 739,
    label: 'Pipeline: 282 / 739 zdjęć',
  });
  assert.equal(jobProgressLabel(imageImport), 'Pipeline: 282 / 739 zdjęć');
  assert.equal(jobProgressPercent(imageImport), (282 / 739) * 100);

  const sourcePhase = job({
    ...imageImport,
    progress: {
      ...imageImport.progress,
      current: 500,
      stage: 'image_source:image_originals_copied',
    },
  });
  assert.equal(jobProgressLabel(sourcePhase), 'Oryginały: 500 / 739 zdjęć');
});

test('summarizes job context and errors for the compact list', () => {
  assert.equal(jobContextLabel(job()), 'Gra game-1');
  assert.equal(
    jobContextLabel(
      job({
        gameId: null,
        inputPayload: { schemaVersion: 1, mobileReleaseId: 'release-1' },
      }),
    ),
    'Wydanie release-1',
  );
  assert.equal(
    jobContextLabel(
      job({
        gameId: null,
        inputPayload: { schemaVersion: 1, datasetVersionId: 'dataset-2' },
      }),
    ),
    'Dataset dataset-2',
  );
  assert.equal(
    jobContextLabel(job({ gameId: null, inputPayload: { schemaVersion: 1 } })),
    'Proces globalny',
  );

  assert.equal(jobErrorSummary(job()), null);
  assert.equal(
    jobErrorSummary(
      job({
        error: { code: 'IMPORT_FAILED', message: 'Nie znaleziono pliku.' },
      }),
    ),
    'IMPORT_FAILED: Nie znaleziono pliku.',
  );
  const shortened = jobErrorSummary(
    job({ error: { code: 'IMPORT_FAILED', message: 'x'.repeat(100) } }),
    32,
  );
  assert.equal(shortened?.length, 32);
  assert.match(shortened ?? '', /…$/);
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
  assert.equal(formatElapsedSeconds(3725), '1 godz. 2 min 5 s');
  assert.equal(formatImageThroughput(null), 'Brak pomiaru');
  assert.match(formatImageThroughput(12.5), /12,5 plików\/min/);
  assert.equal(formatStorageBytes(512), '512 B');
  assert.match(formatStorageBytes(1536), /1,5 KB/);
});

test('ends image import automation when the pipeline reaches manual review', () => {
  const waiting = job({
    inputPayload: {
      schemaVersion: 1,
      importKind: 'image_directory',
      pipelineFingerprint: 'a'.repeat(64),
    },
    jobType: 'import',
    progress: {
      current: 1478,
      failed: 289,
      review: 450,
      stage: 'image_pipeline:manual_review',
      succeeded: 739,
      total: 1478,
    },
    startedAt: '2026-07-27T10:00:00Z',
    status: 'waiting_for_review',
    updatedAt: '2026-07-27T10:46:05Z',
  });

  assert.deepEqual(imageImportAutomationTiming(waiting), {
    completedAt: '2026-07-27T10:46:05Z',
    durationSeconds: 2765,
  });
  assert.equal(
    imageImportAutomationTiming(job({ ...waiting, status: 'processing' })),
    null,
  );
  assert.equal(imageImportAutomationTiming(job()), null);
});
