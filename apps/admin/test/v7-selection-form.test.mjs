import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createV7SelectionPayload,
  deriveV7OutputDirectory,
  normalizeV7SelectionForm,
  parseV7PageBoundary,
} from '../src/features/semi-automatic-image-selection/v7-selection-form.ts';

const defaults = {
  borderStyle: 'top_and_sides',
  direction: 'ascending',
  mode: 'semi_automatic',
};

test('normalizes ascending full-page boundaries to increasing API bounds', () => {
  const result = normalizeV7SelectionForm({
    ...defaults,
    firstPage: '1-9',
    lastPage: '19–27',
  });

  assert.deepEqual(result, {
    ok: true,
    value: {
      ...defaults,
      direction: 'ascending',
      expectedRangeCount: 3,
      firstPage: { end: 9, start: 1 },
      firstSequenceNumber: 1,
      lastPage: { end: 27, start: 19 },
      lastSequenceNumber: 27,
    },
  });
});

test('keeps API bounds increasing when recording pages descend', () => {
  const result = normalizeV7SelectionForm({
    ...defaults,
    direction: 'descending',
    firstPage: '19-27',
    lastPage: '1-9',
  });

  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.value.firstSequenceNumber, 1);
  assert.equal(result.value.lastSequenceNumber, 27);
  assert.equal(result.value.expectedRangeCount, 3);
  assert.equal(result.value.direction, 'descending');
});

test('a single page start expands only to its own 3x3 page', () => {
  assert.deepEqual(parseV7PageBoundary('10'), {
    ok: true,
    value: { end: 18, start: 10 },
  });
  const result = normalizeV7SelectionForm({
    ...defaults,
    firstPage: '10',
    lastPage: '28',
  });
  assert.equal(result.ok, true);
  if (!result.ok) return;
  assert.equal(result.value.firstSequenceNumber, 10);
  assert.equal(result.value.lastSequenceNumber, 36);
  assert.equal(result.value.expectedRangeCount, 3);
});

test('rejects incomplete, reversed, nonnumeric and direction-mismatched boundaries', () => {
  for (const [firstPage, lastPage, direction, code] of [
    ['10-17', '19-27', 'ascending', 'V7_BOUNDARY_NOT_FULL_PAGE'],
    ['18-10', '19-27', 'ascending', 'V7_BOUNDARY_INVALID'],
    ['1.5', '19-27', 'ascending', 'V7_BOUNDARY_INVALID'],
    ['19-27', '1-9', 'ascending', 'V7_DIRECTION_MISMATCH'],
  ]) {
    const result = normalizeV7SelectionForm({
      ...defaults,
      direction,
      firstPage,
      lastPage,
    });
    assert.deepEqual(result, { code, ok: false });
  }
});

test('derives the adjacent cut directory without making it a browser output handle', () => {
  assert.equal(
    deriveV7OutputDirectory('C:\\photos\\1 - 19810'),
    'C:\\photos\\1 - 19810 cut',
  );
  assert.equal(
    deriveV7OutputDirectory('C:\\photos\\1 - 19810\\'),
    'C:\\photos\\1 - 19810 cut',
  );
});

test('builds only the canonical V7 request without legacy recognizer fields', () => {
  const normalized = normalizeV7SelectionForm({
    ...defaults,
    borderStyle: 'irregular_or_none',
    direction: 'descending',
    firstPage: '19-27',
    lastPage: '1-9',
    mode: 'automatic',
  });
  assert.equal(normalized.ok, true);
  if (!normalized.ok) return;
  const payload = createV7SelectionPayload(normalized.value, 'token');
  assert.deepEqual(payload, {
    direction: 'descending',
    firstSequenceNumber: 1,
    lastSequenceNumber: 27,
    mode: 'v7_selection',
    selectionToken: 'token',
    v7: { borderStyle: 'irregular_or_none', mode: 'automatic' },
  });
  assert.equal('recognizerVariant' in payload, false);
});
