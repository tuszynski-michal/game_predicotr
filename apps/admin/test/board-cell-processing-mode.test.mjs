import assert from 'node:assert/strict';
import test from 'node:test';

import {
  boardCellProcessingJobLabel,
  boardCellProcessingModeLabel,
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

test('uses verified v19 processing as the default for new imports', () => {
  assert.equal(DEFAULT_BOARD_CELL_PROCESSING_MODE, 'verified_v19');
  assert.match(boardCellProcessingModeLabel('verified_v19'), /v20/);
  assert.equal(
    boardCellProcessingModeLabel('historical_v18'),
    'v18 — tryb historyczny',
  );
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
