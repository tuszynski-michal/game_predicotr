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

test('batch preparation isolates failures and uses bounded state files', () => {
  assert.match(source, /prepareAllSelectedImageCrops/u);
  assert.match(source, /markReviewed: false/u);
  assert.match(source, /await yieldToBrowser\(\)/u);
  assert.match(source, /persistPreparationFailure/u);
  assert.match(source, /RESULTS_DIRECTORY/u);
  assert.match(source, /resultShardName/u);
  assert.match(source, /mapSelectedImageCropBatch/u);
  assert.match(source, /SELECTED_IMAGE_CROP_ANALYSIS_BATCH_SIZE/u);
  assert.match(source, /preparationBatches/u);
});

test('filled-gap directory listing includes only direct manifest owners', () => {
  assert.match(
    source,
    /listSelectedImageCropSourceDirectories\(\s*parent:[\s\S]*sourceSelection:/u,
  );
  assert.match(source, /FILLED_GAPS_MANIFEST_NAME/u);
  assert.match(
    source,
    /directoryContainsFile\(handle, FILLED_GAPS_MANIFEST_NAME\)/u,
  );
  assert.match(source, /directory\.getFileHandle\(expectedName\)/u);
  assert.match(source, /isSelectedImageCropSourceDirectoryVisible/u);
});

test('selected image crop save journals before writing and verifies the output', () => {
  const journal = source.indexOf('beginSelectedImageCropWrite(');
  const manifestWrite = source.indexOf(
    'await writeSelectedImageCropSession(',
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
  const saveEnd = source.indexOf(
    'export async function prepareAllSelectedImageCrops',
    journal,
  );
  const saveBody = source.slice(journal, saveEnd);
  assert.match(source, /verifiedSource/u);
  assert.match(
    saveBody,
    /const reviewChanged = !selectedImageCropReviewsEqual[\s\S]*?if \(reviewChanged\)[\s\S]*?writeSelectedImageCropReview/u,
  );
});

test('interrupted conflicting output is retained and sent back to correction', () => {
  assert.match(source, /finalizeRecoveredSelectedImageCropWrite/u);
  assert.match(
    source,
    /updateSelectedImageCropCorrections\([\s\S]*pending\.fileName[\s\S]*true/u,
  );
  assert.doesNotMatch(source, /SELECTED_IMAGE_CROP_RECOVERY_CONFLICT/u);
});

test('preparation prefers an off-main-thread worker with a safe fallback', () => {
  assert.match(source, /prepareSelectedImageCropInWorker/u);
  assert.match(source, /workerResult === null/u);
  assert.match(
    source,
    /proposeSelectedImageCrop\(\s*source,\s*current\.snapshot\.session\.preparationPolicyVersion!/u,
  );
});

test('worker compatibility gets one fresh retry before the current main-thread fallback', async () => {
  const workerClient = await readFile(
    new URL(
      '../src/features/semi-automatic-image-selection/selected-image-crop-worker-client.ts',
      import.meta.url,
    ),
    'utf8',
  );
  const worker = await readFile(
    new URL(
      '../src/features/semi-automatic-image-selection/selected-image-crop-worker.ts',
      import.meta.url,
    ),
    'utf8',
  );

  assert.match(worker, /workerProtocolVersion/u);
  assert.match(workerClient, /selectedImageCropWorkerResultMatchesRequest/u);
  assert.match(workerClient, /canRetryStaleWorker/u);
  assert.match(workerClient, /recoverFromStaleWorker/u);
  assert.match(workerClient, /workerFallbackRequired = true/u);
  assert.match(workerClient, /resolve\(null\)/u);
  assert.match(workerClient, /preparedAnchorCache/u);
  assert.match(workerClient, /browserWorkerConcurrency/u);
  assert.match(worker, /prepareFourPointRegistrationAnchor/u);
  assert.match(worker, /finishFourPointRegisteredCrop/u);
  assert.doesNotMatch(worker, /setTimeout\(resolve, 0\)/u);
});

test('batch preparation holds one per-directory lease and releases it in finally', () => {
  assert.match(source, /withSelectedImageCropPreparationLease/u);
  assert.match(source, /prepareAllSelectedImageCropsUnlocked/u);
  assert.match(source, /saveSelectedImageCropUnlocked/u);
});

test('four-point registration reuses a bounded neighbouring anchor and retries only unresolved crops', () => {
  assert.match(source, /CROP_V12_POLICY/u);
  assert.match(source, /findNearestPreparedCropAnchor/u);
  assert.match(source, /fourPointAnchorFromStructuralEvidence/u);
  assert.match(source, /proposal\.registration\?\.status !== 'registered'/u);
  assert.match(source, /sourceChecksumSha256/u);
  assert.match(source, /findNearestPreparedCropAnchors/u);
  assert.match(source, /for \(const anchor of anchors\)/u);
  assert.match(source, /structural\.labels\.length !== 9/u);
});

test('proposal provenance is persisted and historical sessions require an explicit v4 recalculation', () => {
  assert.match(source, /autoCropProposal: proposal/u);
  assert.match(source, /preparationPolicyVersion/u);
  assert.match(source, /SELECTED_IMAGE_CROP_POLICY_RECALCULATION_REQUIRED/u);
  assert.match(source, /recalculateUnreviewedSelectedImageCrops/u);
  assert.match(source, /selectedImageCropRecalculationFileNames/u);
});

test('explicit v12 upgrade can recalculate automatic warnings without touching operator-only selections', () => {
  assert.match(source, /recalculateAutomaticCorrectionSelectedImageCrops/u);
  assert.match(
    source,
    /selectedImageCropAutomaticCorrectionRecalculationFileNames/u,
  );
  assert.match(source, /preparationPolicyVersion === CROP_V12_POLICY/u);
  assert.match(source, /preparationPolicyVersion: CROP_V12_POLICY/u);
});

test('pristine initialization pins the active policy without relying on a racy manifest-existed flag', () => {
  assert.match(source, /ACTIVE_SELECTED_IMAGE_CROP_POLICY/u);
  assert.match(
    source,
    /preparationPolicyVersion: canAdoptActiveSelectedImageCropPolicy\(\s*migratedWithoutPolicy,\s*\)\s*\? ACTIVE_SELECTED_IMAGE_CROP_POLICY/u,
  );
  assert.doesNotMatch(source, /isNewSession/u);
  const existingSnapshotStart = source.indexOf(
    'const storedSession = await requiredJsonFile',
  );
  const existingSnapshotEnd = source.indexOf(
    'return { inventory: existingInventory, session, review, shards };',
    existingSnapshotStart,
  );
  assert.ok(existingSnapshotStart >= 0);
  assert.ok(existingSnapshotEnd > existingSnapshotStart);
  assert.doesNotMatch(
    source.slice(existingSnapshotStart, existingSnapshotEnd),
    /ACTIVE_SELECTED_IMAGE_CROP_POLICY/u,
  );
});

test('a pristine versionless snapshot adopts v12 before the first prepared crop', () => {
  const preparationStart = source.indexOf(
    'export async function prepareAllSelectedImageCrops',
  );
  const preparationEnd = source.indexOf(
    'export async function recalculateUnreviewedSelectedImageCrops',
    preparationStart,
  );
  const preparation = source.slice(preparationStart, preparationEnd);

  assert.match(preparation, /canAdoptActiveSelectedImageCropPolicy/u);
  assert.match(
    preparation,
    /current = await pinSelectedImageCropPreparationPolicy\(current\)/u,
  );
  assert.match(preparation, /const missing = current\.sourceFiles/u);
});

test('automatic crop warnings stay advisory until the operator selects a correction', () => {
  assert.match(source, /synchronizeAutomaticCorrection/u);
  assert.match(
    source,
    /const reviewReason = selectedImageCropReviewReason\(proposal\)/u,
  );
  assert.match(source, /if \(reviewReason === null\) return prepared/u);
  assert.match(
    source,
    /if \(reviewReason === null\) return prepared;\s*return prepared;/u,
  );
  assert.match(source, /acceptRequiredSelectedImageCropCorrections/u);
  assert.doesNotMatch(
    source.slice(
      source.indexOf('async function synchronizeAutomaticCorrection'),
      source.indexOf('function cropAnchorFromSavedResult'),
    ),
    /selected: true/u,
  );
});

test('output ownership rejects foreign files and source mutation', () => {
  assert.match(source, /SELECTED_IMAGE_CROP_OUTPUT_NOT_EMPTY/u);
  assert.match(source, /SELECTED_IMAGE_CROP_OUTPUT_FOREIGN/u);
  assert.match(source, /SELECTED_IMAGE_CROP_SOURCE_CHANGED/u);
  assert.match(source, /SELECTED_IMAGE_CROP_OUTPUT_CHANGED/u);
});

test('a manifest-named orphan is adopted only after exact rendered checksum proof', () => {
  assert.match(source, /selectedImageCropOutputWriteAction/u);
  assert.match(source, /outputAction === 'reject_changed_output'/u);
  assert.match(source, /if \(outputAction === 'write'\)[\s\S]*writeBlob/u);
  assert.match(
    source,
    /\.\.\.manifest\.entries\.map\(\(entry\) =>[\s\S]*entry\.fileName/u,
  );
});

test('filled-gap mode is checksum-bound and uses a separate output directory', () => {
  assert.match(source, /readActiveFilledGapsManifest/u);
  assert.match(source, /sourceSelection === 'filled_gaps'/u);
  assert.match(source, /SELECTED_IMAGE_CROP_FILLED_GAP_MISSING/u);
  assert.match(source, /SELECTED_IMAGE_CROP_FILLED_GAP_CHANGED/u);
  assert.match(source, /SELECTED_IMAGE_CROP_FILLED_GAPS_OUTPUT_SUFFIX/u);
});
