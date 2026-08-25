import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const monitorSource = await readFile(
  new URL('../src/features/jobs/job-monitor.tsx', import.meta.url),
  'utf8',
);

test('keeps the jobs workspace compact and filters only by status', () => {
  assert.match(monitorSource, /Wszystkie statusy/);
  assert.match(monitorSource, /JOB_STATUS_OPTIONS\.map/);
  assert.doesNotMatch(monitorSource, /Wszystkie typy/);
  assert.doesNotMatch(monitorSource, /JOB_TYPE_OPTIONS/);
  assert.doesNotMatch(monitorSource, /typeFilter/);
});

test('shows operational essentials before expanding technical details', () => {
  assert.match(monitorSource, /<details className={`jobCard/);
  assert.match(monitorSource, /<summary className="jobCardSummary">/);
  assert.match(monitorSource, /jobContextLabel\(job\)/);
  assert.match(monitorSource, /jobSourceRangeLabel\(job\)/);
  assert.match(monitorSource, /jobWorkflowLabel\(job\)/);
  assert.match(monitorSource, /jobErrorSummary\(job\)/);
  assert.match(monitorSource, /jobProgressLabel\(job\)/);
  assert.match(monitorSource, /imageImportAutomationTiming\(job\)/);
  assert.match(monitorSource, /Automatyka zakończona/);
  assert.match(monitorSource, /Import i pipeline zakończone/);
  assert.match(monitorSource, /Czas automatycznego przetwarzania/);
  assert.match(monitorSource, /className="jobCardDetails"/);
});

test('preserves polling, retry, cancellation and image diagnostics', () => {
  assert.match(monitorSource, /window\.setInterval/);
  assert.match(monitorSource, /retryJob\(api, job\.id\)/);
  assert.match(monitorSource, /cancelJob\(api, job\.id\)/);
  assert.match(monitorSource, /<ImageJobOperationsPanel/);
});

test('requires an exact typed prefix before deleting a cancelled selection job', () => {
  assert.match(monitorSource, /canDeleteImageSelectionJob\(job\)/);
  assert.match(
    monitorSource,
    /deleteCancelledImageSelectionJob\(api, job\.id\)/,
  );
  assert.match(monitorSource, /job\.id\.slice\(0, 8\)/);
  assert.match(monitorSource, /folder wybranych/);
});

test('shows independent worker health even when the job list is empty', () => {
  assert.match(monitorSource, /loadWorkerLanes\(api\)/);
  assert.match(monitorSource, /Status lokalnych workerów/);
  assert.match(monitorSource, /General/);
  assert.match(monitorSource, /Selekcja zdjęć/);
  assert.match(monitorSource, /Brak świeżego sygnału/);
});
