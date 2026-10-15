import assert from 'node:assert/strict';
import test from 'node:test';
import { recordingSourceIds } from '../src/features/model-quality/recording-groups-state.ts';

const source = (n) => `11111111-1111-4111-8111-${String(n).padStart(12, '0')}`;

test('explicit source pages preserve order and reject oversized or duplicate intent', () => {
  assert.deepEqual(
    recordingSourceIds(`${source(3)};\n${source(1)}, ${source(2)}`),
    [source(3), source(1), source(2)],
  );
  assert.equal(
    recordingSourceIds(
      Array.from({ length: 200 }, (_, i) => source(i)).join('\n'),
    ).length,
    200,
  );
  assert.throws(
    () =>
      recordingSourceIds(
        Array.from({ length: 201 }, (_, i) => source(i)).join('\n'),
      ),
    /200/,
  );
  assert.throws(
    () => recordingSourceIds(`${source(1)} ${source(1)}`),
    /powtórzone/,
  );
  assert.throws(() => recordingSourceIds(''), /1 do 200/);
  assert.throws(() => recordingSourceIds('path/to/photo.jpg'), /UUID/);
});
