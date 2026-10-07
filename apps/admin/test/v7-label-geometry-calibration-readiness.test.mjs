import assert from 'node:assert/strict';
import test from 'node:test';

import { calculateV7LabelGeometryCalibrationReadiness } from '../src/features/v7-label-geometry/v7-label-geometry-calibration-readiness.ts';

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
      sources.map((item, index) => [
        item.sourceId,
        index < 3 ? 'capture-a' : 'capture-b',
      ]),
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
    result.positions.map((position) => [
      position.sourceCount,
      position.captureGroupCount,
    ]),
    Array.from({ length: 9 }, () => [5, 2]),
  );
});

test('unavailable, clipped, uncertain, missing capture group, and duplicate SHA never satisfy readiness', () => {
  const sources = [
    source(1),
    source(2),
    source(3),
    source(4),
    {
      sourceChecksumSha256: source(4).sourceChecksumSha256,
      sourceId: 'source-duplicate',
    },
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
      {
        cropAssessment: null,
        positionIndex: 0,
        sourceId: 'source-6',
        state: 'unavailable',
      },
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
      sources.map((item, index) => [
        item.sourceId,
        index < 3 ? 'capture-a' : 'capture-b',
      ]),
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

test('V2 readiness excludes a sparse photo from profile evidence and retains its diagnostic', () => {
  const sources = Array.from({ length: 6 }, (_, index) => source(index + 1));
  const fullSlots = sources.slice(0, 5).flatMap((item) =>
    Array.from({ length: 9 }, (_, positionIndex) => ({
      cropAssessment: 'contained',
      positionIndex,
      sourceId: item.sourceId,
      state: 'annotated',
    })),
  );
  const captureGroups = Object.fromEntries(
    sources.map((item, index) => [item.sourceId, index < 3 ? 'A' : 'B']),
  );
  // Four points in one row and a column cannot define a V2 lattice.
  const sparseSlots = [0, 1, 2, 3].map((positionIndex) => ({
    cropAssessment: 'contained',
    positionIndex,
    sourceId: 'source-6',
    state: 'annotated',
  }));
  const dynamic = calculateV7LabelGeometryCalibrationReadiness({
    captureGroups,
    geometryFamilyId: 'standard_3x3_numeric_labels_v2',
    slots: [...fullSlots, ...sparseSlots],
    sources,
  });
  assert.deepEqual(dynamic.incompleteLatticeSourceIds, ['source-6']);
  assert.equal(dynamic.readyForProfileCheck, true);
  assert.equal(dynamic.captureGroupCount, 2);
  assert.equal(dynamic.positions[0].sourceCount, 5);
  assert.equal(dynamic.positions[0].containedAnnotationCount, 5);

  const withoutSparse = calculateV7LabelGeometryCalibrationReadiness({
    captureGroups,
    geometryFamilyId: 'standard_3x3_numeric_labels_v2',
    slots: fullSlots,
    sources,
  });
  assert.deepEqual(withoutSparse.incompleteLatticeSourceIds, []);
  assert.equal(withoutSparse.readyForProfileCheck, true);

  const staticFamily = calculateV7LabelGeometryCalibrationReadiness({
    captureGroups,
    geometryFamilyId: 'standard_3x3_numeric_labels_v1',
    slots: [...fullSlots, ...sparseSlots],
    sources,
  });
  assert.deepEqual(staticFamily.incompleteLatticeSourceIds, []);
  assert.equal(staticFamily.readyForProfileCheck, true);
  assert.equal(staticFamily.positions[0].sourceCount, 6);
});

test('V2 accepts an occluded number with five readable sources and two complete-grid groups', () => {
  const sources = Array.from({ length: 11 }, (_, index) => source(index + 1));
  const captureGroups = Object.fromEntries(
    sources.map((item, index) => [item.sourceId, index < 4 ? 'A' : 'B']),
  );
  const slots = sources.slice(0, 10).flatMap((item, index) =>
    Array.from({ length: 9 }, (_, positionIndex) => ({
      cropAssessment: index < 4 && positionIndex === 6 ? null : 'contained',
      positionIndex,
      sourceId: item.sourceId,
      state: index < 4 && positionIndex === 6 ? 'unavailable' : 'annotated',
    })),
  );
  slots.push({
    cropAssessment: 'contained',
    positionIndex: 8,
    sourceId: 'source-11',
    state: 'annotated',
  });
  const result = calculateV7LabelGeometryCalibrationReadiness({
    captureGroups,
    geometryFamilyId: 'standard_3x3_numeric_labels_v2',
    slots,
    sources,
  });
  assert.equal(result.readyForProfileCheck, true);
  assert.equal(result.captureGroupCount, 2);
  assert.deepEqual(result.incompleteLatticeSourceIds, ['source-11']);
  assert.deepEqual(result.positions[6], {
    captureGroupCount: 1,
    containedAnnotationCount: 6,
    incompleteAnnotationCount: 0,
    positionIndex: 6,
    readyForProfileCheck: true,
    sourceCount: 6,
    unavailableCount: 4,
  });
  assert.equal(result.positions[8].sourceCount, 10);
  const legacy = calculateV7LabelGeometryCalibrationReadiness({
    captureGroups,
    geometryFamilyId: 'standard_3x3_numeric_labels_v1',
    slots,
    sources,
  });
  assert.equal(legacy.readyForProfileCheck, false);
  assert.equal(legacy.positions[6].readyForProfileCheck, false);
});

test('a sparse second group and unavailable points never satisfy V2 coverage', () => {
  const sources = Array.from({ length: 7 }, (_, index) => source(index + 1));
  const slots = sources.slice(0, 6).flatMap((item) =>
    Array.from({ length: 9 }, (_, positionIndex) => ({
      cropAssessment: 'contained',
      positionIndex,
      sourceId: item.sourceId,
      state: 'annotated',
    })),
  );
  const captureGroups = Object.fromEntries(
    sources.map((item) => [item.sourceId, 'B']),
  );
  captureGroups['source-7'] = 'A';
  slots.push({
    cropAssessment: 'contained',
    positionIndex: 6,
    sourceId: 'source-7',
    state: 'annotated',
  });
  const result = calculateV7LabelGeometryCalibrationReadiness({
    captureGroups,
    geometryFamilyId: 'standard_3x3_numeric_labels_v2',
    slots,
    sources,
  });
  assert.equal(result.captureGroupCount, 1);
  assert.equal(result.readyForProfileCheck, false);
  assert.equal(result.positions[6].sourceCount, 6);
  assert.deepEqual(result.incompleteLatticeSourceIds, ['source-7']);
});
