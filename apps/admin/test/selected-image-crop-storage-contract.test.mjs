import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(
  new URL(
    '../src/features/semi-automatic-image-selection/selected-image-crop-storage.ts',
    import.meta.url,
  ),
  'utf8',
);

test('selected image crop renderer applies EXIF once and keeps a 1:1 full-width band', () => {
  assert.match(source, /imageOrientation: 'from-image'/u);
  assert.match(source, /canvas\.width = crop\.width/u);
  assert.match(source, /canvas\.height = outputHeight/u);
  assert.match(
    source,
    /context\.drawImage\([\s\S]*crop\.topY[\s\S]*crop\.width[\s\S]*outputHeight/u,
  );
  assert.doesNotMatch(source, /rotate\(|perspective|homograph/iu);
});

test('automatic proposal analyzes only a bounded EXIF-canonical preview', () => {
  assert.match(source, /proposeSelectedImageCrop/u);
  assert.match(source, /SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH/u);
  assert.match(source, /imageOrientation: 'from-image'/u);
  assert.match(source, /detectSelectedImageCropBand/u);
  assert.match(source, /getImageData\(0, 0, width, height\)/u);
});

test('selected image crop save journals before writing and verifies the output', () => {
  const journal = source.indexOf('beginSelectedImageCropWrite(');
  const manifestWrite = source.indexOf(
    'writeSelectedImageCropManifest(input.outputDirectory, manifest)',
    journal,
  );
  const imageWrite = source.indexOf('await writeBlob(', manifestWrite);
  const verification = source.indexOf('verifiedChecksum', imageWrite);
  const finalization = source.indexOf(
    'finalizeSelectedImageCropWrite(',
    verification,
  );
  assert.ok(journal >= 0 && journal < manifestWrite);
  assert.ok(manifestWrite < imageWrite);
  assert.ok(imageWrite < verification);
  assert.ok(verification < finalization);
});

test('output ownership rejects foreign files and source mutation', () => {
  assert.match(source, /SELECTED_IMAGE_CROP_OUTPUT_NOT_EMPTY/u);
  assert.match(source, /SELECTED_IMAGE_CROP_OUTPUT_FOREIGN/u);
  assert.match(source, /SELECTED_IMAGE_CROP_SOURCE_CHANGED/u);
  assert.match(source, /SELECTED_IMAGE_CROP_OUTPUT_CHANGED/u);
});
