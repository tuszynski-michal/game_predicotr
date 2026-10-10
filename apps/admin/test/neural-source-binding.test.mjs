import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  initialNeuralSourceDraft,
  buildNeuralSourceBinding,
  confirmedNeuralRange,
  readNeuralSourceDraft,
  writeNeuralSourceDraft,
  neuralBindingMatchesProposal,
} from '../src/features/imports/neural-source-binding-state.ts';
const nodes = Array.from({ length: 24 }, (_, i) => ({
  x: 0.125 + (i % 6) * 20,
  y: 0.375 + Math.floor(i / 6) * 20,
}));
function proposal(start = 101, end = 105, upper = 500000) {
  return {
    contractVersion: 'neural-grid-proposal-v1',
    gameId: 'g',
    sourceSelectionId: 'source',
    sourceChecksumSha256: 'a'.repeat(64),
    sourceWidth: 1200,
    sourceHeight: 900,
    originalRange: { sequenceRangeStart: start, sequenceRangeEnd: end },
    engineSnapshot: {
      contractVersion: 'grid-engine-manifest-v1',
      expectedLayoutCount: upper,
      model: {},
    },
    proposalChecksumSha256: 'b'.repeat(64),
    detections: ['a', 'b', 'd', 'e', 'extra'].map((detectionId) => ({
      detectionId,
      score: 0.9,
      latticeNodes: nodes,
      cellQuads: [],
      cellVisibility: Array(15).fill('full'),
      structurallyValid: true,
      reasonCodes: [],
    })),
  };
}
test('five positions retain missing103 and reject extra explicitly without compaction', () => {
  const p = proposal(),
    d = {
      ...initialNeuralSourceDraft(p),
      rangeConfirmed: true,
      choices: { a: '0', b: '1', d: '3', e: '4', extra: 'ignore' },
      missing: [2],
    };
  const binding = buildNeuralSourceBinding(p, d);
  assert.deepEqual(
    binding.assignments.map((a) => a.positionIndex),
    [0, 1, 3, 4],
  );
  assert.deepEqual(binding.missingPositionIndexes, [2]);
  assert.deepEqual(binding.ignoredDetectionIds, ['extra']);
  assert.equal(
    binding.confirmedRange.sequenceRangeStart +
      binding.assignments[2].positionIndex,
    104,
  );
  assert.equal(binding.sourceChecksumSha256, p.sourceChecksumSha256);
  assert.throws(
    () => buildNeuralSourceBinding(p, { ...d, missing: [] }),
    /brakujące/,
  );
  assert.throws(
    () =>
      buildNeuralSourceBinding(p, {
        ...d,
        choices: { ...d.choices, extra: '' },
      }),
    /każde wykrycie/,
  );
  assert.throws(
    () =>
      buildNeuralSourceBinding(p, { ...d, choices: { ...d.choices, d: '1' } }),
    /innego/,
  );
});

test('machine ordered binding remains an unconfirmed draft until explicit operator confirmation', () => {
  const p = proposal(),
    draft = {
      ...initialNeuralSourceDraft(p),
      rangeConfirmed: true,
      choices: { a: '0', b: '1', d: '3', e: '4', extra: 'ignore' },
      missing: [2],
    };
  const binding = buildNeuralSourceBinding(p, draft);
  const machineDraft = initialNeuralSourceDraft(p, binding);
  assert.equal(machineDraft.rangeConfirmed, false);
  assert.deepEqual(machineDraft.choices, draft.choices);
  assert.throws(
    () => buildNeuralSourceBinding(p, machineDraft),
    /Potwierdź numery/,
  );
  assert.equal(initialNeuralSourceDraft(p, binding, true).rangeConfirmed, true);
});

test('same-SHA human binding from another upload cannot prefill or confirm a new proposal', () => {
  const p = proposal(),
    draft = {
      ...initialNeuralSourceDraft(p),
      rangeConfirmed: true,
      choices: { a: '0', b: '1', d: '3', e: '4', extra: 'ignore' },
      missing: [2],
    },
    binding = buildNeuralSourceBinding(p, draft);
  const other = { ...binding, sourceSelectionId: 'other-upload' };
  assert.equal(neuralBindingMatchesProposal(p, other), false);
  const fresh = initialNeuralSourceDraft(p, other, true);
  assert.equal(fresh.rangeConfirmed, false);
  assert.deepEqual(fresh.choices, {});
  assert.equal(fresh.rangeStart, '101');
  assert.equal(
    neuralBindingMatchesProposal(p, {
      ...binding,
      proposalChecksumSha256: 'c'.repeat(64),
    }),
    false,
  );
});
test('out-of-bounds filename requires explicit range correction and preserves original provenance', () => {
  const p = proposal(499996, 500004),
    initial = initialNeuralSourceDraft(p);
  assert.equal(initial.rangeEnd, '500004');
  assert.equal(initial.rangeConfirmed, false);
  assert.throws(() => confirmedNeuralRange(p, initial), /granic/);
  const d = {
    ...initial,
    rangeEnd: '500000',
    rangeConfirmed: true,
    choices: { a: '0', b: '1', d: '3', e: '4', extra: 'ignore' },
    missing: [2],
  };
  const binding = buildNeuralSourceBinding(p, d);
  assert.equal(binding.originalRange.sequenceRangeEnd, 500004);
  assert.equal(binding.confirmedRange.sequenceRangeEnd, 500000);
  assert.throws(
    () => buildNeuralSourceBinding(p, { ...d, rangeConfirmed: false }),
    /Potwierdź numery/,
  );
});
test('restart retains exact submitted command; changed proposal or revision requires fresh draft', () => {
  const p = proposal(),
    draft = {
      ...initialNeuralSourceDraft(p),
      rangeConfirmed: true,
      choices: { a: '0', b: '1', d: '3', e: '4', extra: 'ignore' },
      missing: [2],
    };
  const scope = {
    gameId: 'g',
    uploadId: 'u',
    sourceChecksumSha256: p.sourceChecksumSha256,
    proposalChecksumSha256: p.proposalChecksumSha256,
    manifestChecksumSha256: 'c'.repeat(64),
    overrideRevision: 0,
  };
  const command = {
    gameId: 'g',
    sourceChecksumSha256: p.sourceChecksumSha256,
    neuralProposalBinding: buildNeuralSourceBinding(p, draft),
    finalQuads: [],
    expectedOverrideRevision: 0,
  };
  const data = new Map(),
    store = {
      getItem: (k) => data.get(k) ?? null,
      setItem: (k, v) => data.set(k, v),
      removeItem: (k) => data.delete(k),
    };
  writeNeuralSourceDraft(store, scope, { draft, submittedCommand: command });
  assert.deepEqual(
    readNeuralSourceDraft(store, scope).submittedCommand,
    command,
  );
  assert.throws(
    () => readNeuralSourceDraft(store, { ...scope, overrideRevision: 1 }),
    /wcześniejszej/,
  );
  assert.throws(
    () =>
      readNeuralSourceDraft(store, {
        ...scope,
        proposalChecksumSha256: 'd'.repeat(64),
      }),
    /wcześniejszej/,
  );
});
