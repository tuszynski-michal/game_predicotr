import assert from 'node:assert/strict';
import test from 'node:test';

import {
  formatSegmentRange,
  missingReasonLabel,
  parseSequenceRangeQuery,
  summaryState,
} from '../src/features/imports/missing-boards-state.ts';

test('parseSequenceRangeQuery accepts a bare number', () => {
  const result = parseSequenceRangeQuery('12', 500);
  assert.deepEqual(result, { ok: true, range: { from: 12, to: 12 } });
});

test('parseSequenceRangeQuery accepts a hyphen range', () => {
  const result = parseSequenceRangeQuery('10-20', 500);
  assert.deepEqual(result, { ok: true, range: { from: 10, to: 20 } });
});

test('parseSequenceRangeQuery accepts an en-dash range', () => {
  const result = parseSequenceRangeQuery('10–20', 500);
  assert.deepEqual(result, { ok: true, range: { from: 10, to: 20 } });
});

test('parseSequenceRangeQuery trims surrounding and inner whitespace', () => {
  const result = parseSequenceRangeQuery(' 5 - 7 ', 500);
  assert.deepEqual(result, { ok: true, range: { from: 5, to: 7 } });
});

test('parseSequenceRangeQuery treats an empty query as the whole range', () => {
  const result = parseSequenceRangeQuery('   ', 500);
  assert.deepEqual(result, { ok: true, range: null });
});

test('parseSequenceRangeQuery rejects zero', () => {
  const result = parseSequenceRangeQuery('0', 500);
  assert.equal(result.ok, false);
});

test('parseSequenceRangeQuery rejects a range with start greater than end', () => {
  const result = parseSequenceRangeQuery('20-10', 500);
  assert.equal(result.ok, false);
});

test('parseSequenceRangeQuery rejects a number above the expected count', () => {
  const result = parseSequenceRangeQuery('600', 500);
  assert.equal(result.ok, false);
});

test('parseSequenceRangeQuery rejects non-numeric text', () => {
  const result = parseSequenceRangeQuery('abc', 500);
  assert.equal(result.ok, false);
});

test('formatSegmentRange formats a single number', () => {
  assert.equal(formatSegmentRange(1200, 1200), '1200');
});

test('formatSegmentRange formats a range with an en dash', () => {
  assert.equal(formatSegmentRange(1200, 1500), '1200–1500');
});

test('formatSegmentRange applies pl-PL thousands grouping above four digits', () => {
  assert.equal(
    formatSegmentRange(499991, 500000),
    `${(499991).toLocaleString('pl-PL')}–${(500000).toLocaleString('pl-PL')}`,
  );
});

test('missingReasonLabel covers all seven priority codes', () => {
  assert.equal(missingReasonLabel('import_in_progress'), 'W trakcie importu');
  assert.equal(
    missingReasonLabel('waiting_for_geometry'),
    'Oczekuje na siatkę/cięcie',
  );
  assert.equal(missingReasonLabel('partial_source'), 'Niepełne zdjęcie');
  assert.equal(missingReasonLabel('failed'), 'Błąd importu');
  assert.equal(missingReasonLabel('rejected'), 'Odrzucona w weryfikacji');
  assert.equal(
    missingReasonLabel('unknown'),
    'Niekompletna — przyczyna nieustalona',
  );
  assert.equal(missingReasonLabel('no_source'), 'Brak źródła w systemie');
});

function summaryInput(overrides = {}) {
  return {
    loading: false,
    error: null,
    hasStaleData: false,
    expectedLayoutCount: 20,
    countsAdded: 10,
    countsMissing: 10,
    missingByReason: { no_source: 10 },
    segmentCount: 3,
    ...overrides,
  };
}

test('summaryState is loading while a request is in flight', () => {
  assert.equal(summaryState(summaryInput({ loading: true })), 'loading');
});

test('summaryState is error when a request failed with no prior data', () => {
  assert.equal(
    summaryState(summaryInput({ error: 'boom', hasStaleData: false })),
    'error',
  );
});

test('summaryState prefers stale data over a blocking error banner', () => {
  assert.notEqual(
    summaryState(summaryInput({ error: 'boom', hasStaleData: true })),
    'error',
  );
});

test('summaryState is unknown-target when the expected count is missing or invalid', () => {
  assert.equal(
    summaryState(summaryInput({ expectedLayoutCount: null })),
    'unknown-target',
  );
  assert.equal(
    summaryState(summaryInput({ expectedLayoutCount: 0 })),
    'unknown-target',
  );
});

test('summaryState is empty when nothing has been added and only no_source traces exist', () => {
  assert.equal(
    summaryState(
      summaryInput({
        countsAdded: 0,
        countsMissing: 20,
        missingByReason: { no_source: 20 },
      }),
    ),
    'empty',
  );
});

test('summaryState is all-added when nothing is missing', () => {
  assert.equal(
    summaryState(summaryInput({ countsAdded: 20, countsMissing: 0 })),
    'all-added',
  );
});

test('summaryState is no-results when the searched window returns no segments', () => {
  assert.equal(summaryState(summaryInput({ segmentCount: 0 })), 'no-results');
});

test('summaryState is list otherwise', () => {
  assert.equal(summaryState(summaryInput()), 'list');
});
