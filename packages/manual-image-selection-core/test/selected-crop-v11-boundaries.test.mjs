import assert from 'node:assert/strict';
import test from 'node:test';
import {
  boundStructuralCrop,
  validateStructuralEvidence,
  findNumberRegions,
} from '../src/auto-crop-v11-boundaries.ts';

test('valid label is ranked after width validation, not hidden by a narrow fragment', () => {
  const width = 180,
    height = 180,
    rgba = new Uint8ClampedArray(width * height * 4);
  const paint = (left, top, right, bottom) => {
    for (let y = top; y < bottom; y++)
      for (let x = left; x < right; x++)
        if ((x - left) % 4 < 2)
          rgba.set([255, 255, 255, 255], (y * width + x) * 4);
  };
  // Narrow glare at the bottom passes row transitions but not label width.
  paint(75, 116, 87, 120);
  paint(55, 125, 115, 131);
  const found = findNumberRegions({ width, height, rgba }, [
    { left: 20, top: 20, right: 160, bottom: 120 },
  ]);
  assert.equal(found.length, 1);
  assert.equal(found[0].top, 125);
  assert.equal(found[0].bottom, 131);
});
import {
  requiredSelectedImageCropCorrections,
  effectiveSelectedImageCropCorrections,
  replaceSelectedImageCropCorrections,
  markSelectedImageCropCorrected,
} from '../src/crop-session.ts';
const boards = Array.from({ length: 9 }, (_, i) => ({
  left: 20 + (i % 3) * 120,
  top: 200 + Math.floor(i / 3) * 90 + (i % 3) * 10,
  right: 120 + (i % 3) * 120,
  bottom: 260 + Math.floor(i / 3) * 90 + (i % 3) * 10,
}));
const layout = {
  status: 'detected',
  reason: 'complete_layout',
  boards,
  candidateCount: 9,
  analysisWidth: 540,
  analysisHeight: 960,
};
const labels = boards.map((b) => ({
  left: b.left + 20,
  right: b.right - 20,
  top: b.bottom + 2,
  bottom: b.bottom + 15,
}));
test('both boundaries use extrema including sloping bottom numbers and buffer', () => {
  const result = boundStructuralCrop(layout, labels, {
    width: 1080,
    height: 1920,
  });
  assert.equal(result.status, 'detected');
  assert.equal(result.crop.topY, 378);
  assert.equal(result.crop.bottomY, 972);
  validateStructuralEvidence(result);
});
test('missing labels and incomplete source support retain the FULL original', () => {
  for (const result of [
    boundStructuralCrop(layout, labels.slice(0, 8), {
      width: 1080,
      height: 1920,
    }),
    boundStructuralCrop(
      { ...layout, status: 'needs_manual_crop', reason: 'incomplete_layout' },
      [],
      { width: 1080, height: 1920 },
    ),
  ]) {
    assert.equal(result.status, 'needs_manual_crop');
    assert.equal(result.crop.topY, 0);
    assert.equal(result.crop.bottomY, 1920);
    validateStructuralEvidence(result);
    assert.throws(
      () =>
        validateStructuralEvidence({
          ...result,
          crop: { ...result.crop, topY: 5 },
        }),
      /EVIDENCE_INVALID/,
    );
  }
});
test('required correction survives deselection and JSON restart; explicit review resolves it', () => {
  const structural = boundStructuralCrop(layout, [], {
    width: 1080,
    height: 1920,
  });
  let snapshot = {
    inventory: { entries: [{ fileName: 'seq_1-9.jpg' }] },
    shards: [
      { results: { 'seq_1-9.jpg': { autoCropProposal: { structural } } } },
    ],
    review: {
      reviewedFileNames: [],
      correctedFileNames: [],
      correctionFileNames: ['seq_1-9.jpg'],
      correctionCursor: 0,
    },
  };
  snapshot.review = replaceSelectedImageCropCorrections(snapshot.review, []);
  snapshot = JSON.parse(JSON.stringify(snapshot));
  assert.deepEqual(requiredSelectedImageCropCorrections(snapshot), [
    'seq_1-9.jpg',
  ]);
  assert.deepEqual(effectiveSelectedImageCropCorrections(snapshot), [
    'seq_1-9.jpg',
  ]);
  snapshot.review = markSelectedImageCropCorrected(
    snapshot.review,
    'seq_1-9.jpg',
  );
  assert.deepEqual(requiredSelectedImageCropCorrections(snapshot), []);
});
