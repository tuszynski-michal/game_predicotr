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
    'v0.10 — historyczny tryb pomiarowy',
  );
  assert.equal(
    boardCellProcessingModeLabel('structured_default'),
    'v0.10 v2 — stabilny silnik strukturalny',
  );
  assert.equal(
    boardCellProcessingModeLabel('structured_lattice_v3'),
    'v0.10 v3 — precyzyjna siatka symboli',
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
  const structuredDefault = imageImportJob(undefined, {
    geometryMode: 'structured_default',
  });
  const structuredV3 = imageImportJob(undefined, {
    geometryMode: 'structured_lattice_v3',
  });

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
  assert.equal(
    boardCellProcessingJobLabel(structuredDefault),
    'v0.10 v2 — stabilny silnik strukturalny · wirtualne cropy',
  );
  assert.equal(
    boardCellProcessingJobLabel(structuredV3),
    'v0.10 v3 — precyzyjna siatka symboli · wirtualne cropy',
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
  const structuredDefault = imageImportJob(undefined, {
    geometryMode: 'structured_default',
  });
  const structuredV3 = imageImportJob(undefined, {
    geometryMode: 'structured_lattice_v3',
  });

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
  assert.equal(
    jobMatchesBoardCellProcessingMode(structuredDefault, 'structured_default'),
    true,
  );
  assert.equal(
    jobMatchesBoardCellProcessingMode(shadow, 'structured_default'),
    false,
  );
  assert.equal(
    jobMatchesBoardCellProcessingMode(structuredV3, 'structured_lattice_v3'),
    true,
  );
  assert.equal(
    jobMatchesBoardCellProcessingMode(
      structuredDefault,
      'structured_lattice_v3',
    ),
    false,
  );
});
