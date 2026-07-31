import assert from 'node:assert/strict';
import test from 'node:test';

import { appendUniqueCandidates } from '../src/features/symbols/symbol-image-picker-state.ts';

const candidate = (observationId, confidence = 0.9) => ({
  confidence,
  cropChecksumSha256: observationId.padEnd(64, '0').slice(0, 64),
  observationId,
});

test('candidate pages append in server order without repeating observations', () => {
  const first = [candidate('one'), candidate('two')];
  const next = [candidate('two', 0.8), candidate('three', 0.7)];

  assert.deepEqual(
    appendUniqueCandidates(first, next).map((item) => item.observationId),
    ['one', 'two', 'three'],
  );
});
