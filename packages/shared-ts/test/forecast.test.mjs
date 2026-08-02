import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import {
  DomainValidationError,
  calculateTargetForecast,
} from '../dist/index.js';

const fixturePath = new URL(
  '../../domain-fixtures/target-golden-cases.json',
  import.meta.url,
);
const fixture = JSON.parse(await readFile(fixturePath, 'utf8'));

function createInput(testCase) {
  return {
    ...fixture.metadata,
    ...testCase.input,
  };
}

function serializeDynamicResult(result) {
  return {
    evaluatedSpinCount: result.evaluatedSpinCount,
    finalCumulativePayout: result.finalCumulativePayout,
    finalCumulativeCost: result.finalCumulativeCost,
    finalNetCredits: result.finalNetCredits,
    positiveLocalPeaks: result.positiveLocalPeaks,
  };
}

function assertMetadata(result, input) {
  assert.equal(result.mobileReleaseVersion, input.mobileReleaseVersion);
  assert.equal(result.snapshotChecksum, input.snapshotChecksum);
  assert.equal(result.datasetVersion, input.datasetVersion);
  assert.equal(result.rulesVersion, input.rulesVersion);
  assert.equal(result.algorithmVersion, input.algorithmVersion);
  assert.equal(result.startSequenceNumber, input.startSequenceNumber);
  assert.equal(result.targetScanLimit, input.targetScanLimit);
  assert.equal(result.spinCost, input.spinCost);
}

function assertDomainError(expectedCode, callback) {
  assert.throws(
    callback,
    (error) =>
      error instanceof DomainValidationError && error.code === expectedCode,
  );
}

for (const testCase of fixture.cases) {
  test(`Target golden: ${testCase.id}`, () => {
    const input = createInput(testCase);
    const result = calculateTargetForecast(input);

    assert.ok(
      testCase.manualCalculation.length > 0,
      'Golden case must document manual calculation.',
    );
    assertMetadata(result, input);
    assert.deepEqual(serializeDynamicResult(result), testCase.expected);
  });
}

test('Target is deterministic, immutable and does not mutate input', () => {
  const input = createInput(fixture.cases[4]);
  const inputBefore = structuredClone(input);

  const first = calculateTargetForecast(input);
  const second = calculateTargetForecast(input);

  assert.deepEqual(first, second);
  assert.deepEqual(input, inputBefore);
  assert.ok(Object.isFrozen(first));
  assert.ok(Object.isFrozen(first.positiveLocalPeaks));
  assert.ok(first.positiveLocalPeaks.every((peak) => Object.isFrozen(peak)));
});

test('Target rejects invalid length and sequence integrity failures', () => {
  const valid = createInput(fixture.cases[8]);

  assertDomainError('invalid_forecast_length', () =>
    calculateTargetForecast({
      ...valid,
      sequencePayouts: valid.sequencePayouts.slice(0, -1),
    }),
  );
  assertDomainError('invalid_forecast_length', () =>
    calculateTargetForecast({
      ...valid,
      sequencePayouts: [
        ...valid.sequencePayouts,
        { sequenceNumber: 1, payoutCredits: 0 },
      ],
    }),
  );
  assertDomainError('sequence_integrity_error', () =>
    calculateTargetForecast({
      ...valid,
      sequencePayouts: valid.sequencePayouts.map((value, index) =>
        index === 1
          ? { ...value, sequenceNumber: value.sequenceNumber + 1 }
          : value,
      ),
    }),
  );
  assertDomainError('sequence_integrity_error', () =>
    calculateTargetForecast({
      ...valid,
      sequencePayouts: valid.sequencePayouts.map((value, index) =>
        index === 2
          ? {
              ...value,
              sequenceNumber: valid.sequencePayouts[1].sequenceNumber,
            }
          : value,
      ),
    }),
  );
});

test('Target rejects invalid domain values and metadata', () => {
  const valid = createInput(fixture.cases[8]);

  assertDomainError('invalid_payout', () =>
    calculateTargetForecast({
      ...valid,
      sequencePayouts: valid.sequencePayouts.map((value, index) =>
        index === 0 ? { ...value, payoutCredits: -1 } : value,
      ),
    }),
  );
  assertDomainError('invalid_spin_cost', () =>
    calculateTargetForecast({ ...valid, spinCost: -1 }),
  );
  assertDomainError('invalid_target_scan_limit', () =>
    calculateTargetForecast({ ...valid, targetScanLimit: 0 }),
  );
  assertDomainError('invalid_target_scan_limit', () =>
    calculateTargetForecast({ ...valid, targetScanLimit: 500_001 }),
  );
  assertDomainError('invalid_sequence_number', () =>
    calculateTargetForecast({ ...valid, startSequenceNumber: 0 }),
  );
  assertDomainError('invalid_layout_count', () =>
    calculateTargetForecast({
      ...valid,
      layoutCount: 0,
      sequencePayouts: [],
    }),
  );
  assertDomainError('invalid_forecast_metadata', () =>
    calculateTargetForecast({ ...valid, snapshotChecksum: 'invalid' }),
  );
});

test('Target rejects cumulative values outside safe integer range', () => {
  const maximum = Number.MAX_SAFE_INTEGER;
  const input = {
    ...fixture.metadata,
    startSequenceNumber: 1,
    layoutCount: 3,
    targetScanLimit: 2,
    spinCost: maximum,
    sequencePayouts: [
      { sequenceNumber: 2, payoutCredits: maximum },
      { sequenceNumber: 3, payoutCredits: 0 },
    ],
  };

  assertDomainError('forecast_numeric_overflow', () =>
    calculateTargetForecast(input),
  );
});

test('Target evaluates only the bounded cyclic prefix', () => {
  const input = {
    ...fixture.metadata,
    layoutCount: 6,
    startSequenceNumber: 5,
    targetScanLimit: 3,
    sequencePayouts: [
      { sequenceNumber: 6, payoutCredits: 20 },
      { sequenceNumber: 1, payoutCredits: 20 },
      { sequenceNumber: 2, payoutCredits: 0 },
    ],
  };

  const result = calculateTargetForecast(input);

  assert.equal(result.targetScanLimit, 3);
  assert.equal(result.evaluatedSpinCount, 3);
  assert.equal(result.finalCumulativePayout, 40);
  assert.equal(result.finalCumulativeCost, 30);
  assert.equal(result.finalNetCredits, 10);
  assert.deepEqual(result.positiveLocalPeaks, [
    {
      cumulativeCost: 20,
      cumulativePayout: 40,
      netCredits: 20,
      sequenceNumber: 1,
      spinNumber: 2,
      spinPayout: 20,
    },
  ]);
});
