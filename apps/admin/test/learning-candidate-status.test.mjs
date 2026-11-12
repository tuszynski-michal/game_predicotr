import assert from 'node:assert/strict';
import test from 'node:test';
import {
  candidateRunSuffix,
  candidateSummary,
} from '../src/features/model-quality/learning-candidate-status.ts';

const later = {
  versionId: 'bf327cfa-b35c-5c79-95bd-707301b703a5',
  isDefault: true,
  assignedToGame: true,
  laterEvaluation: true,
  latestEvaluation: {
    evaluationId: '6f7bcc1d-70c2-414d-ad92-ceeced1dc710',
    reportId: '0c2e483e-082a-5f2e-a65d-313503a7d911',
    verdict: 'PASS',
    policyVersion: 'grid-model-per-game-gate-v4',
    createdAt: '2026-11-12T08:03:15Z',
  },
};

test('a later PASS and current use are shown next to the pinned REVISE', () => {
  assert.equal(
    candidateRunSuffix(later),
    ' → później PASS (bramka v4) · w użyciu: domyślny i przypisany do gry',
  );
  assert.deepEqual(candidateSummary(later, 'REVISE'), [
    'Wynik uczenia (REVISE) to pierwotna ocena tego przebiegu i nie zmienia się.',
    'Ten sam kandydat ma nowszą ocenę: PASS (bramka v4, ocena 6f7bcc1d).',
    'Kandydat bf327cfa jest obecnie domyślny i przypisany do gry.',
  ]);
});

test('the learning own evaluation adds no later-evaluation claim', () => {
  const own = {
    ...later,
    laterEvaluation: false,
    isDefault: false,
    assignedToGame: false,
  };
  assert.equal(candidateRunSuffix(own), '');
  assert.deepEqual(candidateSummary(own, 'REVISE'), [
    'Kandydat bf327cfa nie jest obecnie używany.',
  ]);
});

test('a learning without a candidate renders nothing extra', () => {
  assert.equal(candidateRunSuffix(undefined), '');
  assert.equal(candidateSummary(null, null), null);
});
