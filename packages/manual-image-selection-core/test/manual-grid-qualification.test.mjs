import assert from 'node:assert/strict';
import test from 'node:test';
import {
  automaticUnavailableGridCells,
  completeManualGridFlags,
  manualGridQualification,
  manualGridCellPolygons,
  manualGridVerticalCropWarning,
} from '../src/manual-grid-qualification.ts';

const quad = [
  { x: 0, y: 0 },
  { x: 299, y: 0 },
  { x: 299, y: 199 },
  { x: 0, y: 199 },
];

test('side truncation differs from an upstream top or bottom crop error', () => {
  assert.equal(
    manualGridVerticalCropWarning(
      quad.map((p) => ({ ...p, x: p.x - 20 })),
      200,
    ),
    false,
  );
  assert.equal(
    manualGridVerticalCropWarning(
      quad.map((p) => ({ ...p, y: p.y - 20 })),
      200,
    ),
    true,
  );
  assert.equal(
    manualGridVerticalCropWarning(
      quad.map((p) => ({ ...p, y: p.y + 20 })),
      200,
    ),
    true,
  );
});
test('complete source retains all fifteen projective cells, including floating point edges', () => {
  for (const value of [
    quad,
    [
      { x: 3, y: 0 },
      { x: 298, y: 7 },
      { x: 289, y: 199 },
      { x: 0, y: 192 },
    ],
  ]) {
    assert.deepEqual(automaticUnavailableGridCells(value, 300, 200), []);
    assert.equal(manualGridCellPolygons(value).length, 15);
    assert.equal(
      manualGridQualification(completeManualGridFlags, value, 300, 200)
        .excludeFromGeometryTraining,
      false,
    );
  }
});
test('outside core creates automatic mask; partial declarations and full missing boards are explicit', () => {
  const shifted = quad.map((p) => ({ ...p, y: p.y - 10 }));
  assert.deepEqual(
    automaticUnavailableGridCells(shifted, 300, 200),
    [0, 1, 2, 3, 4],
  );
  assert.throws(
    () => manualGridQualification(completeManualGridFlags, shifted, 300, 200),
    /Niepełną|niepełną/,
  );
  const result = manualGridQualification(
    { partial: true, exclude: false, manualUnavailable: [14] },
    shifted,
    300,
    200,
  );
  assert.deepEqual(result.unavailableCellIndices, [0, 1, 2, 3, 4, 14]);
  assert.equal(result.exclusionReason, 'missing_pixels');
  assert.equal(result.excludeFromGeometryTraining, true);
  assert.throws(
    () =>
      manualGridQualification(
        { partial: true, exclude: true, manualUnavailable: [] },
        quad,
        300,
        200,
      ),
    /co najmniej/,
  );
  assert.equal(
    manualGridQualification(
      {
        partial: true,
        exclude: true,
        manualUnavailable: Array.from({ length: 15 }, (_, i) => i),
      },
      quad,
      300,
      200,
    ).unavailableCellIndices.length,
    15,
  );
});
test('uncertain decoration excludes geometry without removing visible symbols', () => {
  const result = manualGridQualification(
    { ...completeManualGridFlags, exclude: true },
    quad,
    300,
    200,
  );
  assert.equal(result.completenessStatus, 'complete');
  assert.equal(result.exclusionReason, 'manual_exclusion');
  assert.deepEqual(result.unavailableCellIndices, []);
});
