import assert from 'node:assert/strict';
import test from 'node:test';
import {
  neuralImportSnapshot,
  neuralImportModelExportId,
  isNeuralGeometryPreflight,
} from '../src/features/imports/neural-import-preflight-state.ts';

const snapshot = {
  contractVersion: 'neural-grid-proposal-snapshot-v2',
  gameId: 'game',
  gameConfiguration: 'neural_grid_v3',
  expectedLayoutCount: 500000,
  catalogueManifestSha256: 'a'.repeat(64),
  catalogueManifest: {
    modelKind: 'neural_grid',
    schemaVersion: 'grid-model-catalogue-v1',
    familyCode: 'third_geometry',
    versionId: 'pinned-version',
    inferenceManifest: { exportId: 'third-export' },
  },
};
const job = {
  gameId: 'game',
  jobType: 'validate',
  inputPayload: {
    preflightPolicyVersion: 'page-geometry-preflight-v13-neural-mumie-pilot',
    neuralGridProposal: snapshot,
  },
};

test('Admin recognizes a third catalogue family and keeps its complete snapshot', () => {
  assert.deepEqual(neuralImportSnapshot(job), snapshot);
  assert.equal(isNeuralGeometryPreflight(job), true);
  assert.equal(neuralImportModelExportId(job), 'third-export');
  assert.equal(neuralImportSnapshot({ ...job, gameId: 'other' }), null);
});
