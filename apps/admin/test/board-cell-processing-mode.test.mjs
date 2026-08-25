import assert from 'node:assert/strict';
import test from 'node:test';

import {
  boardCellProcessingJobLabel,
  boardCellProcessingModeLabel,
  boardCellProcessingModeRequiresConfirmation,
  canStartBoardCellProcessingMode,
  DEFAULT_BOARD_CELL_PROCESSING_MODE,
  jobMatchesBoardCellProcessingMode,
  VERIFIED_V19_ACTIVATION_VERSION,
} from '../src/features/imports/board-cell-processing-mode.ts';

function imageImportJob(boardCellProcessing) {
  return {
    id: 'job-1',
    inputPayload: {
      importKind: 'image_directory',
      ...(boardCellProcessing === undefined ? {} : { boardCellProcessing }),
    },
    jobType: 'import',
    status: 'created',
  };
}

test('keeps historical v18 as the unconfirmed default', () => {
  assert.equal(DEFAULT_BOARD_CELL_PROCESSING_MODE, 'historical_v18');
  assert.equal(
    boardCellProcessingModeRequiresConfirmation('historical_v18'),
    false,
  );
  assert.equal(canStartBoardCellProcessingMode('historical_v18', false), true);
  assert.equal(
    boardCellProcessingModeLabel('historical_v18'),
    'v18 — tryb historyczny',
  );
});

test('requires an explicit confirmation before starting verified v19', () => {
  assert.equal(
    boardCellProcessingModeRequiresConfirmation('verified_v19'),
    true,
  );
  assert.equal(canStartBoardCellProcessingMode('verified_v19', false), false);
  assert.equal(canStartBoardCellProcessingMode('verified_v19', true), true);
  assert.match(boardCellProcessingModeLabel('verified_v19'), /v20/);
});

test('labels each persisted import with its pinned board processing engine', () => {
  const historical = imageImportJob(undefined);
  const verified = imageImportJob({
    activationVersion: VERIFIED_V19_ACTIVATION_VERSION,
  });

  assert.equal(
    boardCellProcessingJobLabel(historical),
    'v18 — tryb historyczny',
  );
  assert.equal(
    boardCellProcessingJobLabel(verified),
    'v20 — geometria i cropy v19',
  );
});

test('rejects a returned job whose immutable snapshot differs from the selected mode', () => {
  const historical = imageImportJob(undefined);
  const verified = imageImportJob({
    activationVersion: VERIFIED_V19_ACTIVATION_VERSION,
  });

  assert.equal(
    jobMatchesBoardCellProcessingMode(historical, 'historical_v18'),
    true,
  );
  assert.equal(
    jobMatchesBoardCellProcessingMode(historical, 'verified_v19'),
    false,
  );
  assert.equal(
    jobMatchesBoardCellProcessingMode(verified, 'verified_v19'),
    true,
  );
  assert.equal(
    jobMatchesBoardCellProcessingMode(verified, 'historical_v18'),
    false,
  );
});
