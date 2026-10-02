import assert from 'node:assert/strict';
import test from 'node:test';

import {
  boardCellProcessingJobLabel,
  boardCellProcessingModeLabel,
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

test('offers labels only for the virtual import policies', () => {
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
    'v20 — geometria i cropy v19 (usunięty)',
  );
  assert.equal(
    boardCellProcessingJobLabel(shadow),
    '0.10 — nowy silnik w cieniu · primary v20/v19 (usunięty)',
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

test('a returned job matches only its own virtual policy', () => {
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

  for (const legacy of [historical, verified, shadow]) {
    assert.equal(
      jobMatchesBoardCellProcessingMode(legacy, 'structured_default'),
      false,
    );
    assert.equal(
      jobMatchesBoardCellProcessingMode(legacy, 'structured_lattice_v3'),
      false,
    );
  }
  assert.equal(
    jobMatchesBoardCellProcessingMode(structuredDefault, 'structured_default'),
    true,
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
