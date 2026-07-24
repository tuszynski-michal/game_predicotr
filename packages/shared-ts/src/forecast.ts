import type {
  ForecastInput,
  ForecastPeak,
  ForecastResult,
} from './contracts.js';
import { DomainValidationError } from './errors.js';

const SNAPSHOT_CHECKSUM_PATTERN = /^[0-9a-f]{64}$/i;

function validatePositiveInteger(
  value: number,
  code: 'invalid_layout_count' | 'invalid_forecast_metadata',
  label: string,
): void {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new DomainValidationError(
      code,
      `${label} must be a positive safe integer.`,
    );
  }
}

function validateMetadata(input: ForecastInput): void {
  if (
    typeof input.mobileReleaseVersion !== 'string' ||
    typeof input.algorithmVersion !== 'string' ||
    typeof input.snapshotChecksum !== 'string' ||
    input.mobileReleaseVersion.trim().length === 0 ||
    input.algorithmVersion.trim().length === 0 ||
    !SNAPSHOT_CHECKSUM_PATTERN.test(input.snapshotChecksum)
  ) {
    throw new DomainValidationError(
      'invalid_forecast_metadata',
      'Forecast versions and snapshot checksum must be valid.',
    );
  }
  validatePositiveInteger(
    input.datasetVersion,
    'invalid_forecast_metadata',
    'Dataset version',
  );
  validatePositiveInteger(
    input.rulesVersion,
    'invalid_forecast_metadata',
    'Rules version',
  );
}

function validateInput(input: ForecastInput): void {
  validateMetadata(input);
  validatePositiveInteger(
    input.layoutCount,
    'invalid_layout_count',
    'Layout count',
  );
  if (
    !Number.isSafeInteger(input.startSequenceNumber) ||
    input.startSequenceNumber < 1 ||
    input.startSequenceNumber > input.layoutCount
  ) {
    throw new DomainValidationError(
      'invalid_sequence_number',
      'Start sequence number must belong to the dataset.',
    );
  }
  if (!Number.isSafeInteger(input.spinCost) || input.spinCost < 0) {
    throw new DomainValidationError(
      'invalid_spin_cost',
      'Spin cost must be a non-negative safe integer.',
    );
  }

  const expectedSpinCount = input.layoutCount - 1;
  if (input.sequencePayouts.length !== expectedSpinCount) {
    throw new DomainValidationError(
      'invalid_forecast_length',
      `Forecast contains ${input.sequencePayouts.length} spins; expected ${expectedSpinCount}.`,
    );
  }
}

function expectedSequenceNumber(
  startSequenceNumber: number,
  layoutCount: number,
  spinNumber: number,
): number {
  const positionsUntilWrap = layoutCount - startSequenceNumber + 1;
  if (spinNumber < positionsUntilWrap) {
    return startSequenceNumber + spinNumber;
  }
  return spinNumber - positionsUntilWrap + 1;
}

function checkedAdd(left: number, right: number): number {
  const result = left + right;
  if (!Number.isSafeInteger(result)) {
    throw new DomainValidationError(
      'forecast_numeric_overflow',
      'Forecast cumulative credits exceed the safe integer range.',
    );
  }
  return result;
}

function freezePeak(peak: ForecastPeak): ForecastPeak {
  return Object.freeze(peak);
}

export function calculateTargetForecast(input: ForecastInput): ForecastResult {
  validateInput(input);

  let cumulativePayout = 0;
  let cumulativeCost = 0;
  let previousNet = 0;
  let peakCandidate: ForecastPeak | null = null;
  const positiveLocalPeaks: ForecastPeak[] = [];

  for (
    let payoutIndex = 0;
    payoutIndex < input.sequencePayouts.length;
    payoutIndex += 1
  ) {
    const spinNumber = payoutIndex + 1;
    const sequencePayout = input.sequencePayouts[payoutIndex];
    if (sequencePayout === undefined) {
      throw new DomainValidationError(
        'sequence_integrity_error',
        'Forecast sequence contains an unexpected gap.',
      );
    }

    const expectedSequence = expectedSequenceNumber(
      input.startSequenceNumber,
      input.layoutCount,
      spinNumber,
    );
    if (
      !Number.isSafeInteger(sequencePayout.sequenceNumber) ||
      sequencePayout.sequenceNumber !== expectedSequence
    ) {
      throw new DomainValidationError(
        'sequence_integrity_error',
        `Spin ${spinNumber} must use sequence ${expectedSequence}.`,
      );
    }
    if (
      !Number.isSafeInteger(sequencePayout.payoutCredits) ||
      sequencePayout.payoutCredits < 0
    ) {
      throw new DomainValidationError(
        'invalid_payout',
        'Every precomputed payout must be a non-negative safe integer.',
      );
    }

    cumulativePayout = checkedAdd(
      cumulativePayout,
      sequencePayout.payoutCredits,
    );
    cumulativeCost = checkedAdd(cumulativeCost, input.spinCost);
    const netCredits = cumulativePayout - cumulativeCost;
    if (!Number.isSafeInteger(netCredits)) {
      throw new DomainValidationError(
        'forecast_numeric_overflow',
        'Forecast net credits exceed the safe integer range.',
      );
    }

    const currentPoint: ForecastPeak = {
      spinNumber,
      sequenceNumber: sequencePayout.sequenceNumber,
      spinPayout: sequencePayout.payoutCredits,
      cumulativePayout,
      cumulativeCost,
      netCredits,
    };

    if (netCredits > previousNet) {
      peakCandidate = currentPoint;
    } else if (netCredits < previousNet) {
      if (peakCandidate !== null && peakCandidate.netCredits > 0) {
        positiveLocalPeaks.push(freezePeak(peakCandidate));
      }
      peakCandidate = null;
    }
    previousNet = netCredits;
  }

  if (peakCandidate !== null && peakCandidate.netCredits > 0) {
    positiveLocalPeaks.push(freezePeak(peakCandidate));
  }

  return Object.freeze({
    mobileReleaseVersion: input.mobileReleaseVersion,
    snapshotChecksum: input.snapshotChecksum,
    datasetVersion: input.datasetVersion,
    rulesVersion: input.rulesVersion,
    algorithmVersion: input.algorithmVersion,
    startSequenceNumber: input.startSequenceNumber,
    evaluatedSpinCount: input.layoutCount - 1,
    spinCost: input.spinCost,
    finalCumulativePayout: cumulativePayout,
    finalCumulativeCost: cumulativeCost,
    finalNetCredits: cumulativePayout - cumulativeCost,
    positiveLocalPeaks: Object.freeze(positiveLocalPeaks),
  });
}
