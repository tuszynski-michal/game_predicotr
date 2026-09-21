import assert from 'node:assert/strict';
import test from 'node:test';

import {
  calculateV7LabelGeometryCalibrationReadiness,
} from '../src/features/v7-label-geometry/v7-label-geometry-calibration-readiness.ts';

function source(index) {
  return {
    sourceChecksumSha256: `${index}`.repeat(64).slice(0, 64),
    sourceId: `source-${index}`,
  };
}

test('readiness requires five unique SHA values and two capture groups per position', () => {
  const sources = Array.from({ length: 5 }, (_, index) => source(index + 1));
  const result = calculateV7LabelGeometryCalibrationReadiness({
    captureGroups: Object.fromEntries(
      sources.map((item, index) => [item.sourceId, index < 3 ? 'capture-a' : 'capture-b']),
    ),
    slots: sources.flatMap((item) =>
      Array.from({ length: 9 }, (_, positionIndex) => ({
        cropAssessment: 'contained',
        positionIndex,
        sourceId: item.sourceId,
        state: 'annotated',
      })),
    ),
    sources,
  });

  assert.equal(result.readyForProfileCheck, true);
  assert.deepEqual(
    result.positions.map((position) => [position.sourceCount, position.captureGroupCount]),
    Array.from({ length: 9 }, () => [5, 2]),
  );
});

test('unavailable, clipped, uncertain, missing capture group, and duplicate SHA never satisfy readiness', () => {
  const sources = [
    source(1),
    source(2),
    source(3),
    source(4),
    { sourceChecksumSha256: source(4).sourceChecksumSha256, sourceId: 'source-duplicate' },
    source(6),
  ];
  const result = calculateV7LabelGeometryCalibrationReadiness({
    captureGroups: {
      'source-1': 'capture-a',
      'source-2': 'capture-a',
      'source-3': 'capture-b',
      'source-4': 'capture-b',
      'source-duplicate': 'capture-c',
    },
    slots: [
      ...sources.slice(0, 4).map((item) => ({
        cropAssessment: 'contained',
        positionIndex: 0,
        sourceId: item.sourceId,
        state: 'annotated',
      })),
      {
        cropAssessment: 'clipped',
        positionIndex: 0,
        sourceId: 'source-duplicate',
        state: 'annotated',
      },
      {
        cropAssessment: 'uncertain',
        positionIndex: 0,
        sourceId: 'source-6',
        state: 'annotated',
      },
      { cropAssessment: null, positionIndex: 0, sourceId: 'source-6', state: 'unavailable' },
    ],
    sources,
  });

  assert.equal(result.readyForProfileCheck, false);
  assert.deepEqual(result.positions[0], {
    captureGroupCount: 2,
    containedAnnotationCount: 4,
    incompleteAnnotationCount: 2,
    positionIndex: 0,
    readyForProfileCheck: false,
    sourceCount: 4,
    unavailableCount: 1,
  });
  assert.equal(result.positions[1]?.readyForProfileCheck, false);
});

test('diagnostic clipped annotations do not block five contained points', () => {
  const sources = Array.from({ length: 6 }, (_, index) => source(index + 1));
  const result = calculateV7LabelGeometryCalibrationReadiness({
    captureGroups: Object.fromEntries(
      sources.map((item, index) => [item.sourceId, index < 3 ? 'capture-a' : 'capture-b']),
    ),
    slots: [
      ...sources.slice(0, 5).map((item) => ({
        cropAssessment: 'contained',
        positionIndex: 0,
        sourceId: item.sourceId,
        state: 'annotated',
      })),
      {
        cropAssessment: 'clipped',
        positionIndex: 0,
        sourceId: sources[5].sourceId,
        state: 'annotated',
      },
    ],
    sources,
  });

  assert.equal(result.positions[0]?.sourceCount, 5);
  assert.equal(result.positions[0]?.captureGroupCount, 2);
  assert.equal(result.positions[0]?.incompleteAnnotationCount, 1);
  assert.equal(result.positions[0]?.readyForProfileCheck, true);
});
