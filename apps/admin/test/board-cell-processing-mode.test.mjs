import assert from 'node:assert/strict';
import test from 'node:test';

import {
  boardCellProcessingJobLabel,
  boardCellProcessingModeLabel,
  DEFAULT_BOARD_CELL_PROCESSING_MODE,
  jobMatchesBoardCellProcessingMode,
  VERIFIED_V19_ACTIVATION_VERSION,
} from '../src/features/imports/board-cell-processing-mode.ts';

function imageImportJob(boardCellProcessing, imageGeometryRollout) {
  return {
    id: 'job-1',
    inputPayload: {
      importKind: 'image_directory',
      ...(boardCellProcessing === undefined ? {} : { boardCellProcessing }),
      ...(imageGeometryRollout === undefined ? {} : { imageGeometryRollout }),
    },
    jobType: 'import',
    status: 'created',
  };
}

test('uses verified v19 processing as the default for new imports', () => {
  assert.equal(DEFAULT_BOARD_CELL_PROCESSING_MODE, 'verified_v19');
  assert.match(boardCellProcessingModeLabel('verified_v19'), /v20/);
  assert.equal(
    boardCellProcessingModeLabel('structured_shadow'),
    '0.10 — geometria strukturalna w cieniu',
  );
});

test('labels each persisted import with its pinned board processing engine', () => {
  const historical = imageImportJob(undefined);
  const verified = imageImportJob({
    activationVersion: VERIFIED_V19_ACTIVATION_VERSION,
  });
  const shadow = imageImportJob(
    { activationVersion: VERIFIED_V19_ACTIVATION_VERSION },
    { geometryMode: 'structured_shadow' },
  );

  assert.equal(
    boardCellProcessingJobLabel(historical),
    'v18 — tryb historyczny',
  );
  assert.equal(
    boardCellProcessingJobLabel(verified),
    'v20 — geometria i cropy v19',
  );
  assert.equal(
    boardCellProcessingJobLabel(shadow),
    '0.10 — nowy silnik w cieniu · primary v20/v19',
  );
});

test('rejects a returned job whose immutable snapshot differs from the game policy', () => {
  const historical = imageImportJob(undefined);
  const verified = imageImportJob({
    activationVersion: VERIFIED_V19_ACTIVATION_VERSION,
  });
  const shadow = imageImportJob(
    { activationVersion: VERIFIED_V19_ACTIVATION_VERSION },
    { geometryMode: 'structured_shadow' },
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
    jobMatchesBoardCellProcessingMode(shadow, 'verified_v19'),
    false,
  );
  assert.equal(
    jobMatchesBoardCellProcessingMode(verified, 'structured_shadow'),
    false,
  );
  assert.equal(
    jobMatchesBoardCellProcessingMode(shadow, 'structured_shadow'),
    true,
  );
});
