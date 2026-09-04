'use client';

import {
  approvePreparedSelectedImageCrop,
  beginSelectedImageCropWrite,
  createSelectedImageCropManifest,
  finalizeSelectedImageCropWrite,
  rollbackSelectedImageCropWrite,
  selectedImageCropRecoveryAction,
  validateSelectedImageCropBand,
  validateSelectedImageCropManifest,
  validateSelectedImageCropSources,
  SELECTED_IMAGE_CROP_JPEG_QUALITY,
  type SelectedImageCropBand,
  type SelectedImageCropManifestV1,
  type SelectedImageCropSourceEntry,
} from '@game-predictor/manual-image-selection-core/crop';
import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH,
  type SelectedImageAutoCropProposal,
} from '@game-predictor/manual-image-selection-core/auto-crop';

import { pickLocalDirectory } from '@/lib/local-directory-picker';

export const SELECTED_IMAGE_CROP_MANIFEST_NAME =
  'manual-image-crop-output-v1.json';
type SelectedImageCropPermissionMode = 'read' | 'readwrite';

export interface SelectedImageCropSourceFile extends SelectedImageCropSourceEntry {
  readonly handle: FileSystemFileHandle;
  readonly relativePath: string;
}

export interface PreparedSelectedImageCropDirectory {
  readonly sourceDirectory: FileSystemDirectoryHandle;
  readonly outputDirectory: FileSystemDirectoryHandle;
  readonly sourceFiles: readonly SelectedImageCropSourceFile[];
  readonly manifest: SelectedImageCropManifestV1;
}

export interface SelectedImageCropOutputFile {
  readonly handle: FileSystemFileHandle;
  readonly relativePath: string;
}

export interface SelectedImageCropRenderedFile {
  readonly blob: Blob;
  readonly dimensions: { readonly width: number; readonly height: number };
}

export interface SelectedImageCropPreparationProgress {
  readonly completed: number;
  readonly total: number;
  readonly manifest: SelectedImageCropManifestV1;
}

export async function proposeSelectedImageCrop(
  source: File,
): Promise<SelectedImageAutoCropProposal> {
  const bitmap = await createImageBitmap(source, {
    imageOrientation: 'from-image',
  });
  try {
    const width = Math.min(SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH, bitmap.width);
    const height = Math.max(
      1,
      Math.round((bitmap.height * width) / bitmap.width),
    );
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', {
      alpha: false,
      willReadFrequently: true,
    });
    if (context === null) {
      throw new Error('SELECTED_IMAGE_AUTO_CROP_CANVAS_UNAVAILABLE');
    }
    context.drawImage(bitmap, 0, 0, width, height);
    const pixels = context.getImageData(0, 0, width, height);
    return detectSelectedImageCropBand(
      { width, height, rgba: pixels.data },
      { width: bitmap.width, height: bitmap.height },
    );
  } finally {
    bitmap.close();
  }
}

export async function pickSelectedImageCropParentDirectory(): Promise<FileSystemDirectoryHandle> {
  return pickLocalDirectory({
    id: 'gp-selected-image-crop-parent',
    mode: 'readwrite',
  });
}

export async function listSelectedImageCropSourceDirectories(
  parent: FileSystemDirectoryHandle,
): Promise<readonly string[]> {
  await ensureDirectoryPermission(parent, 'readwrite');
  const names: string[] = [];
  for await (const [name, handle] of directoryEntries(parent)) {
    if (handle.kind === 'directory' && !name.endsWith(' cut')) names.push(name);
  }
  return names.sort(naturalCompare);
}

export async function prepareSelectedImageCropDirectory(
  parent: FileSystemDirectoryHandle,
  sourceDirectoryName: string,
): Promise<PreparedSelectedImageCropDirectory> {
  await ensureDirectoryPermission(parent, 'readwrite');
  const sourceDirectory = await parent.getDirectoryHandle(sourceDirectoryName);
  const sourceFiles = await listSelectedImageCropSourceFiles(sourceDirectory);
  const inventoryChecksum =
    await selectedImageCropInventoryChecksum(sourceFiles);
  const outputName = `${sourceDirectoryName} cut`;
  const outputExisted = await directoryContainsEntry(parent, outputName);
  const outputDirectory = await parent.getDirectoryHandle(outputName, {
    create: true,
  });
  await ensureDirectoryPermission(outputDirectory, 'readwrite');

  const existingManifest = await readSelectedImageCropManifest(outputDirectory);
  let manifest: SelectedImageCropManifestV1;
  if (existingManifest !== null) {
    manifest = validateSelectedImageCropManifest(
      existingManifest,
      inventoryChecksum,
    );
    if (manifest.sourceDirectoryName !== sourceDirectoryName)
      throw new Error('SELECTED_IMAGE_CROP_OUTPUT_FOREIGN');
  } else {
    const entries = await listDirectoryEntryNames(outputDirectory);
    if (outputExisted && entries.length > 0)
      throw new Error('SELECTED_IMAGE_CROP_OUTPUT_NOT_EMPTY');
    manifest = createSelectedImageCropManifest({
      sourceDirectoryName,
      outputDirectoryName: outputName,
      sourceInventoryChecksumSha256: inventoryChecksum,
      entries: sourceFiles,
      now: new Date().toISOString(),
    });
    await writeSelectedImageCropManifest(outputDirectory, manifest);
  }

  manifest = await recoverSelectedImageCropWrite(outputDirectory, manifest);
  await assertOwnedOutputContents(outputDirectory, manifest);
  return { sourceDirectory, outputDirectory, sourceFiles, manifest };
}

export async function listSelectedImageCropSourceFiles(
  directory: FileSystemDirectoryHandle,
): Promise<readonly SelectedImageCropSourceFile[]> {
  await ensureDirectoryPermission(directory, 'read');
  const candidates: Array<{
    readonly fileName: string;
    readonly sizeBytes: number;
    readonly lastModifiedMs: number;
    readonly handle: FileSystemFileHandle;
  }> = [];
  const invalidJpegs: string[] = [];
  for await (const [name, handle] of directoryEntries(directory)) {
    if (handle.kind !== 'file') continue;
    if (!/\.jpe?g$/iu.test(name)) continue;
    if (!/^seq_\d+-\d+\.jpe?g$/iu.test(name)) {
      invalidJpegs.push(name);
      continue;
    }
    const file = await handle.getFile();
    candidates.push({
      fileName: name,
      sizeBytes: file.size,
      lastModifiedMs: file.lastModified,
      handle,
    });
  }
  if (invalidJpegs.length > 0)
    throw new Error(
      `SELECTED_IMAGE_CROP_INVALID_NAMES:${invalidJpegs.join(',')}`,
    );
  const validated = validateSelectedImageCropSources(candidates);
  const byName = new Map(
    candidates.map((file) => [file.fileName, file.handle]),
  );
  return validated.map((entry) => ({
    ...entry,
    handle: byName.get(entry.fileName)!,
    relativePath: entry.fileName,
  }));
}

export async function renderSelectedImageCrop(
  source: File,
  crop: SelectedImageCropBand,
): Promise<SelectedImageCropRenderedFile> {
  validateSelectedImageCropBand(crop);
  const bitmap = await createImageBitmap(source, {
    imageOrientation: 'from-image',
  });
  try {
    if (bitmap.width !== crop.width || bitmap.height !== crop.height)
      throw new Error('SELECTED_IMAGE_CROP_SOURCE_DIMENSIONS_CHANGED');
    const outputHeight = crop.bottomY - crop.topY;
    const canvas = document.createElement('canvas');
    canvas.width = crop.width;
    canvas.height = outputHeight;
    const context = canvas.getContext('2d');
    if (context === null)
      throw new Error('SELECTED_IMAGE_CROP_CANVAS_UNAVAILABLE');
    context.drawImage(
      bitmap,
      0,
      crop.topY,
      crop.width,
      outputHeight,
      0,
      0,
      crop.width,
      outputHeight,
    );
    const blob = await canvasToBlob(
      canvas,
      'image/jpeg',
      SELECTED_IMAGE_CROP_JPEG_QUALITY,
    );
    return { blob, dimensions: { width: crop.width, height: outputHeight } };
  } finally {
    bitmap.close();
  }
}

export async function saveSelectedImageCrop(input: {
  readonly outputDirectory: FileSystemDirectoryHandle;
  readonly sourceFile: SelectedImageCropSourceFile;
  readonly crop: SelectedImageCropBand;
  readonly manifest: SelectedImageCropManifestV1;
  readonly markReviewed?: boolean;
  readonly render?: (
    source: File,
    crop: SelectedImageCropBand,
  ) => Promise<SelectedImageCropRenderedFile>;
}): Promise<SelectedImageCropManifestV1> {
  const render = input.render ?? renderSelectedImageCrop;
  const currentSource = await input.sourceFile.handle.getFile();
  if (
    currentSource.size !== input.sourceFile.sizeBytes ||
    currentSource.lastModified !== input.sourceFile.lastModifiedMs
  ) {
    throw new Error('SELECTED_IMAGE_CROP_SOURCE_CHANGED');
  }
  const sourceChecksum = await sha256Blob(currentSource);
  const rendered = await render(currentSource, input.crop);
  const outputChecksum = await sha256Blob(rendered.blob);
  const existingResult = input.manifest.entries.find(
    (entry) => entry.fileName === input.sourceFile.fileName,
  )?.result;
  const observedExistingChecksum = await readOptionalFileChecksum(
    input.outputDirectory,
    input.sourceFile.fileName,
  );
  if (
    observedExistingChecksum !== (existingResult?.outputChecksumSha256 ?? null)
  ) {
    throw new Error('SELECTED_IMAGE_CROP_OUTPUT_CHANGED');
  }

  const now = new Date().toISOString();
  let manifest = beginSelectedImageCropWrite(
    input.manifest,
    {
      kind: 'write_crop',
      fileName: input.sourceFile.fileName,
      expectedSourceChecksumSha256: sourceChecksum,
      expectedOutputChecksumSha256: outputChecksum,
      crop: input.crop,
      startedAt: now,
      replacesOutputChecksumSha256:
        existingResult?.outputChecksumSha256 ?? null,
      markReviewed: input.markReviewed,
    },
    now,
  );
  await writeSelectedImageCropManifest(input.outputDirectory, manifest);
  await writeBlob(
    input.outputDirectory,
    input.sourceFile.fileName,
    rendered.blob,
  );
  const verifiedChecksum = await readOptionalFileChecksum(
    input.outputDirectory,
    input.sourceFile.fileName,
  );
  if (verifiedChecksum !== outputChecksum)
    throw new Error('SELECTED_IMAGE_CROP_OUTPUT_CHECKSUM_MISMATCH');
  manifest = finalizeSelectedImageCropWrite(manifest, new Date().toISOString());
  await writeSelectedImageCropManifest(input.outputDirectory, manifest);
  return manifest;
}

export async function approvePreparedSelectedImageCropResult(input: {
  readonly outputDirectory: FileSystemDirectoryHandle;
  readonly fileName: string;
  readonly manifest: SelectedImageCropManifestV1;
}): Promise<SelectedImageCropManifestV1> {
  const manifest = approvePreparedSelectedImageCrop(
    input.manifest,
    input.fileName,
    new Date().toISOString(),
  );
  await writeSelectedImageCropManifest(input.outputDirectory, manifest);
  return manifest;
}

export async function prepareAllSelectedImageCrops(
  prepared: PreparedSelectedImageCropDirectory,
  onProgress?: (progress: SelectedImageCropPreparationProgress) => void,
): Promise<PreparedSelectedImageCropDirectory> {
  let manifest = prepared.manifest;
  const missing = prepared.sourceFiles.filter(
    (source) =>
      manifest.entries.find((entry) => entry.fileName === source.fileName)
        ?.result === null,
  );
  let completed = manifest.entries.length - missing.length;
  onProgress?.({ completed, total: manifest.entries.length, manifest });
  for (const sourceFile of missing) {
    const source = await sourceFile.handle.getFile();
    const proposal = await proposeSelectedImageCrop(source);
    manifest = await saveSelectedImageCrop({
      outputDirectory: prepared.outputDirectory,
      sourceFile,
      crop: proposal.crop,
      manifest,
      markReviewed: false,
    });
    completed += 1;
    onProgress?.({ completed, total: manifest.entries.length, manifest });
    await yieldToBrowser();
  }
  return { ...prepared, manifest };
}

export async function listSelectedImageCropOutputFiles(
  prepared: PreparedSelectedImageCropDirectory,
): Promise<readonly SelectedImageCropOutputFile[]> {
  return Promise.all(
    prepared.sourceFiles.map(async (source) => ({
      handle: await prepared.outputDirectory.getFileHandle(source.fileName),
      relativePath: source.relativePath,
    })),
  );
}

export async function readCanonicalSelectedImageDimensions(
  source: File,
): Promise<{ readonly width: number; readonly height: number }> {
  const bitmap = await createImageBitmap(source, {
    imageOrientation: 'from-image',
  });
  try {
    return { width: bitmap.width, height: bitmap.height };
  } finally {
    bitmap.close();
  }
}

async function recoverSelectedImageCropWrite(
  outputDirectory: FileSystemDirectoryHandle,
  manifest: SelectedImageCropManifestV1,
): Promise<SelectedImageCropManifestV1> {
  const pending = manifest.pendingOperation;
  if (pending === null) return manifest;
  const observed = await readOptionalFileChecksum(
    outputDirectory,
    pending.fileName,
  );
  const action = selectedImageCropRecoveryAction(manifest, observed);
  if (action === 'block_conflicting_output')
    throw new Error('SELECTED_IMAGE_CROP_RECOVERY_CONFLICT');
  const recovered =
    action === 'finalize_matching_output'
      ? finalizeSelectedImageCropWrite(manifest, new Date().toISOString())
      : rollbackSelectedImageCropWrite(manifest, new Date().toISOString());
  await writeSelectedImageCropManifest(outputDirectory, recovered);
  return recovered;
}

async function assertOwnedOutputContents(
  outputDirectory: FileSystemDirectoryHandle,
  manifest: SelectedImageCropManifestV1,
): Promise<void> {
  const allowed = new Set([
    SELECTED_IMAGE_CROP_MANIFEST_NAME.toLocaleLowerCase('en-US'),
    ...manifest.entries
      .filter((entry) => entry.result !== null)
      .map((entry) => entry.fileName.toLocaleLowerCase('en-US')),
  ]);
  if (manifest.pendingOperation !== null)
    allowed.add(manifest.pendingOperation.fileName.toLocaleLowerCase('en-US'));
  for (const name of await listDirectoryEntryNames(outputDirectory)) {
    if (!allowed.has(name.toLocaleLowerCase('en-US')))
      throw new Error(`SELECTED_IMAGE_CROP_OUTPUT_FOREIGN:${name}`);
  }
}

async function readSelectedImageCropManifest(
  directory: FileSystemDirectoryHandle,
): Promise<SelectedImageCropManifestV1 | null> {
  try {
    const handle = await directory.getFileHandle(
      SELECTED_IMAGE_CROP_MANIFEST_NAME,
    );
    const value: unknown = JSON.parse(await (await handle.getFile()).text());
    if (value === null || typeof value !== 'object')
      throw new Error('SELECTED_IMAGE_CROP_MANIFEST_INVALID');
    return validateSelectedImageCropManifest(
      value as SelectedImageCropManifestV1,
    );
  } catch (cause) {
    if (isNotFound(cause)) return null;
    throw cause;
  }
}

export async function writeSelectedImageCropManifest(
  directory: FileSystemDirectoryHandle,
  manifest: SelectedImageCropManifestV1,
): Promise<void> {
  validateSelectedImageCropManifest(manifest);
  const blob = new Blob([`${JSON.stringify(manifest, null, 2)}\n`], {
    type: 'application/json',
  });
  await writeBlob(directory, SELECTED_IMAGE_CROP_MANIFEST_NAME, blob);
}

async function writeBlob(
  directory: FileSystemDirectoryHandle,
  name: string,
  blob: Blob,
): Promise<void> {
  const target = await directory.getFileHandle(name, { create: true });
  const writable = await target.createWritable();
  try {
    await writable.write(blob);
    await writable.close();
  } catch (cause) {
    await writable.abort().catch(() => undefined);
    throw cause;
  }
}

async function readOptionalFileChecksum(
  directory: FileSystemDirectoryHandle,
  name: string,
): Promise<string | null> {
  try {
    const handle = await directory.getFileHandle(name);
    return sha256Blob(await handle.getFile());
  } catch (cause) {
    if (isNotFound(cause)) return null;
    throw cause;
  }
}

async function yieldToBrowser(): Promise<void> {
  await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
}

async function selectedImageCropInventoryChecksum(
  files: readonly SelectedImageCropSourceFile[],
): Promise<string> {
  return sha256Blob(
    new Blob([
      JSON.stringify(
        files.map(({ fileName, sizeBytes, lastModifiedMs }) => ({
          fileName,
          sizeBytes,
          lastModifiedMs,
        })),
      ),
    ]),
  );
}

export async function sha256Blob(blob: Blob): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await blob.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

async function ensureDirectoryPermission(
  directory: FileSystemDirectoryHandle,
  mode: SelectedImageCropPermissionMode,
): Promise<void> {
  const permissionHandle = directory as FileSystemDirectoryHandle & {
    queryPermission(options: {
      mode: SelectedImageCropPermissionMode;
    }): Promise<PermissionState>;
    requestPermission(options: {
      mode: SelectedImageCropPermissionMode;
    }): Promise<PermissionState>;
  };
  const existing = await permissionHandle.queryPermission({ mode });
  if (existing === 'granted') return;
  if ((await permissionHandle.requestPermission({ mode })) !== 'granted')
    throw new Error('SELECTED_IMAGE_CROP_DIRECTORY_PERMISSION_DENIED');
}

function directoryEntries(
  directory: FileSystemDirectoryHandle,
): AsyncIterable<
  readonly [string, FileSystemFileHandle | FileSystemDirectoryHandle]
> {
  return (
    directory as FileSystemDirectoryHandle & {
      entries(): AsyncIterable<
        readonly [string, FileSystemFileHandle | FileSystemDirectoryHandle]
      >;
    }
  ).entries();
}

async function listDirectoryEntryNames(
  directory: FileSystemDirectoryHandle,
): Promise<readonly string[]> {
  const names: string[] = [];
  for await (const [name] of directoryEntries(directory)) names.push(name);
  return names;
}

async function directoryContainsEntry(
  directory: FileSystemDirectoryHandle,
  expectedName: string,
): Promise<boolean> {
  for await (const [name] of directoryEntries(directory)) {
    if (name === expectedName) return true;
  }
  return false;
}

function canvasToBlob(
  canvas: HTMLCanvasElement,
  type: string,
  quality: number,
): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) =>
        blob === null
          ? reject(new Error('SELECTED_IMAGE_CROP_ENCODING_FAILED'))
          : resolve(blob),
      type,
      quality,
    );
  });
}

function isNotFound(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'NotFoundError';
}

function naturalCompare(left: string, right: string): number {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: 'base',
  });
}
