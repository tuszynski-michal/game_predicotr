import assert from 'node:assert/strict';
import test from 'node:test';

import { selectedImageCropOutputWriteAction } from '../src/features/semi-automatic-image-selection/selected-image-crop-output-recovery.ts';

test('output recovery writes only when the recorded state matches the directory', () => {
  assert.equal(
    selectedImageCropOutputWriteAction({
      recordedChecksumSha256: null,
      observedChecksumSha256: null,
      proposedChecksumSha256: 'new',
    }),
    'write',
  );
  assert.equal(
    selectedImageCropOutputWriteAction({
      recordedChecksumSha256: 'old',
      observedChecksumSha256: 'old',
      proposedChecksumSha256: 'new',
    }),
    'write',
  );
});

test('an exact orphan is reused while different bytes remain fail-closed', () => {
  assert.equal(
    selectedImageCropOutputWriteAction({
      recordedChecksumSha256: null,
      observedChecksumSha256: 'new',
      proposedChecksumSha256: 'new',
    }),
    'reuse_matching_bytes',
  );
  assert.equal(
    selectedImageCropOutputWriteAction({
      recordedChecksumSha256: null,
      observedChecksumSha256: 'foreign',
      proposedChecksumSha256: 'new',
    }),
    'reject_changed_output',
  );
  assert.equal(
    selectedImageCropOutputWriteAction({
      recordedChecksumSha256: 'recorded',
      observedChecksumSha256: 'foreign',
      proposedChecksumSha256: 'foreign',
    }),
    'reject_changed_output',
  );
});
