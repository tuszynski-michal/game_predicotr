import assert from 'node:assert/strict';
import test from 'node:test';

import { isSelectedImageCropSourceDirectoryVisible } from '../src/features/semi-automatic-image-selection/selected-image-crop-directory-options.ts';

test('full crop mode hides existing cut outputs', () => {
  assert.equal(
    isSelectedImageCropSourceDirectoryVisible({
      directoryName: '117829 - 128268',
      sourceSelection: 'all',
      hasFilledGapsManifest: false,
    }),
    true,
  );
  assert.equal(
    isSelectedImageCropSourceDirectoryVisible({
      directoryName: '117829 - 128268 cut',
      sourceSelection: 'all',
      hasFilledGapsManifest: true,
    }),
    false,
  );
});

test('filled-gap mode includes manifest owners including cut directories', () => {
  for (const directoryName of ['248176 - 272016', '117829 - 128268 cut'])
    assert.equal(
      isSelectedImageCropSourceDirectoryVisible({
        directoryName,
        sourceSelection: 'filled_gaps',
        hasFilledGapsManifest: true,
      }),
      true,
    );

  assert.equal(
    isSelectedImageCropSourceDirectoryVisible({
      directoryName: '128269 - 149634 cut',
      sourceSelection: 'filled_gaps',
      hasFilledGapsManifest: false,
    }),
    false,
  );
  assert.equal(
    isSelectedImageCropSourceDirectoryVisible({
      directoryName: '117829 - 128268 cut filled-gaps cut',
      sourceSelection: 'filled_gaps',
      hasFilledGapsManifest: true,
    }),
    false,
  );
});
