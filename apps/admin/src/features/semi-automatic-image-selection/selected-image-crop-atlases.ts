'use client';

import type { SelectedImageCropManifestEntry } from '@game-predictor/manual-image-selection-core/crop';

import {
  SELECTED_IMAGE_CROP_ATLAS_DIRECTORY,
  SELECTED_IMAGE_CROP_STATE_DIRECTORY,
  type PreparedSelectedImageCropDirectory,
} from './selected-image-crop-storage';

export const SELECTED_IMAGE_CROP_ATLAS_BATCH_SIZE = 100;
export const SELECTED_IMAGE_CROP_THUMBNAIL_WIDTH = 144;
export const SELECTED_IMAGE_CROP_THUMBNAIL_HEIGHT = 96;
const ATLAS_COLUMNS = 10;
const ATLAS_RENDERER = 'selected-image-crop-atlas-webp-v2';

export interface SelectedImageCropAtlas {
  readonly batchIndex: number;
  readonly imageUrl: string;
  readonly fileNames: readonly string[];
  readonly cacheFileName: string;
}

export async function loadSelectedImageCropAtlases(
  prepared: PreparedSelectedImageCropDirectory,
  onAtlas: (atlas: SelectedImageCropAtlas) => void,
  signal?: AbortSignal,
): Promise<void> {
  const entries = prepared.manifest.entries;
  const activeCacheFiles = new Set<string>();
  for (
    let offset = 0;
    offset < entries.length;
    offset += SELECTED_IMAGE_CROP_ATLAS_BATCH_SIZE
  ) {
    if (signal?.aborted === true) return;
    const batchIndex = Math.floor(
      offset / SELECTED_IMAGE_CROP_ATLAS_BATCH_SIZE,
    );
    const batch = entries.slice(
      offset,
      offset + SELECTED_IMAGE_CROP_ATLAS_BATCH_SIZE,
    );
    const preparedEntries = batch.filter(hasResult);
    if (preparedEntries.length === 0) continue;
    const atlas = await loadOrCreateAtlas(
      prepared,
      batchIndex,
      preparedEntries,
    );
    activeCacheFiles.add(atlas.cacheFileName);
    if (Boolean(signal?.aborted)) {
      URL.revokeObjectURL(atlas.imageUrl);
      return;
    }
    onAtlas(atlas);
    await yieldToBrowser();
  }
  if (!Boolean(signal?.aborted))
    await pruneAtlasDirectory(prepared.outputDirectory, activeCacheFiles);
}

export function selectedImageCropAtlasPosition(entryIndex: number): {
  readonly batchIndex: number;
  readonly x: number;
  readonly y: number;
} {
  const localIndex = entryIndex % SELECTED_IMAGE_CROP_ATLAS_BATCH_SIZE;
  return {
    batchIndex: Math.floor(entryIndex / SELECTED_IMAGE_CROP_ATLAS_BATCH_SIZE),
    x: (localIndex % ATLAS_COLUMNS) * SELECTED_IMAGE_CROP_THUMBNAIL_WIDTH,
    y:
      Math.floor(localIndex / ATLAS_COLUMNS) *
      SELECTED_IMAGE_CROP_THUMBNAIL_HEIGHT,
  };
}

async function loadOrCreateAtlas(
  prepared: PreparedSelectedImageCropDirectory,
  batchIndex: number,
  entries: readonly (SelectedImageCropManifestEntry & {
    readonly result: NonNullable<SelectedImageCropManifestEntry['result']>;
  })[],
): Promise<SelectedImageCropAtlas> {
  const key = await sha256Text(
    JSON.stringify({
      renderer: ATLAS_RENDERER,
      batchIndex,
      entries: entries.map((entry) => [
        entry.fileName,
        entry.result.outputChecksumSha256,
      ]),
    }),
  );
  const atlasDirectory = await atlasDirectoryHandle(prepared.outputDirectory);
  const fileName = `${String(batchIndex).padStart(4, '0')}-${key}.webp`;
  let atlasFile: File;
  try {
    atlasFile = await (await atlasDirectory.getFileHandle(fileName)).getFile();
  } catch (cause) {
    if (!(cause instanceof DOMException && cause.name === 'NotFoundError'))
      throw cause;
    const blob = await renderAtlas(prepared, batchIndex, entries);
    const handle = await atlasDirectory.getFileHandle(fileName, {
      create: true,
    });
    const writable = await handle.createWritable();
    try {
      await writable.write(blob);
      await writable.close();
    } catch (cause) {
      await writable.abort().catch(() => undefined);
      throw cause;
    }
    atlasFile = await handle.getFile();
  }
  return {
    batchIndex,
    imageUrl: URL.createObjectURL(atlasFile),
    fileNames: entries.map((entry) => entry.fileName),
    cacheFileName: fileName,
  };
}

async function renderAtlas(
  prepared: PreparedSelectedImageCropDirectory,
  batchIndex: number,
  entries: readonly (SelectedImageCropManifestEntry & {
    readonly result: NonNullable<SelectedImageCropManifestEntry['result']>;
  })[],
): Promise<Blob> {
  const canvas = document.createElement('canvas');
  canvas.width = ATLAS_COLUMNS * SELECTED_IMAGE_CROP_THUMBNAIL_WIDTH;
  canvas.height =
    Math.ceil(SELECTED_IMAGE_CROP_ATLAS_BATCH_SIZE / ATLAS_COLUMNS) *
    SELECTED_IMAGE_CROP_THUMBNAIL_HEIGHT;
  const context = canvas.getContext('2d', { alpha: false });
  if (context === null)
    throw new Error('SELECTED_IMAGE_CROP_ATLAS_CANVAS_UNAVAILABLE');
  context.fillStyle = '#111827';
  context.fillRect(0, 0, canvas.width, canvas.height);
  for (const entry of entries) {
    const entryIndex = prepared.manifest.entries.findIndex(
      (candidate) => candidate.fileName === entry.fileName,
    );
    const position = selectedImageCropAtlasPosition(entryIndex);
    if (position.batchIndex !== batchIndex) continue;
    const file = await (
      await prepared.outputDirectory.getFileHandle(entry.fileName)
    ).getFile();
    const bitmap = await createImageBitmap(file);
    try {
      const scale = Math.min(
        SELECTED_IMAGE_CROP_THUMBNAIL_WIDTH / bitmap.width,
        SELECTED_IMAGE_CROP_THUMBNAIL_HEIGHT / bitmap.height,
      );
      const width = Math.max(1, Math.round(bitmap.width * scale));
      const height = Math.max(1, Math.round(bitmap.height * scale));
      context.drawImage(
        bitmap,
        position.x +
          Math.floor((SELECTED_IMAGE_CROP_THUMBNAIL_WIDTH - width) / 2),
        position.y +
          Math.floor((SELECTED_IMAGE_CROP_THUMBNAIL_HEIGHT - height) / 2),
        width,
        height,
      );
    } finally {
      bitmap.close();
    }
    await yieldToBrowser();
  }
  return canvasToBlob(canvas, 'image/webp', 0.58);
}

function hasResult(
  entry: SelectedImageCropManifestEntry,
): entry is SelectedImageCropManifestEntry & {
  readonly result: NonNullable<SelectedImageCropManifestEntry['result']>;
} {
  return entry.result !== null;
}

async function atlasDirectoryHandle(
  outputDirectory: FileSystemDirectoryHandle,
): Promise<FileSystemDirectoryHandle> {
  const state = await outputDirectory.getDirectoryHandle(
    SELECTED_IMAGE_CROP_STATE_DIRECTORY,
    { create: true },
  );
  return state.getDirectoryHandle(SELECTED_IMAGE_CROP_ATLAS_DIRECTORY, {
    create: true,
  });
}

async function pruneAtlasDirectory(
  outputDirectory: FileSystemDirectoryHandle,
  activeCacheFiles: ReadonlySet<string>,
): Promise<void> {
  const directory = await atlasDirectoryHandle(outputDirectory);
  const entries = (
    directory as FileSystemDirectoryHandle & {
      entries(): AsyncIterable<readonly [string, FileSystemHandle]>;
    }
  ).entries();
  let removed = 0;
  for await (const [name, handle] of entries) {
    if (
      removed >= 32 ||
      handle.kind !== 'file' ||
      activeCacheFiles.has(name) ||
      !/^\d{4}-[a-f0-9]{64}\.webp$/u.test(name)
    )
      continue;
    await directory.removeEntry(name);
    removed += 1;
  }
}

async function sha256Text(value: string): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(value),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
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
          ? reject(new Error('SELECTED_IMAGE_CROP_ATLAS_ENCODING_FAILED'))
          : resolve(blob),
      type,
      quality,
    );
  });
}

async function yieldToBrowser(): Promise<void> {
  await new Promise<void>((resolve) => window.setTimeout(resolve, 0));
}
