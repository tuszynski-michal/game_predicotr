import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';

import sharp from 'sharp';

import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_POLICY,
  SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH,
} from '../packages/manual-image-selection-core/src/auto-crop.ts';

const [parentArg, fromArg = '1', throughArg = '999'] = process.argv.slice(2);
if (!parentArg) {
  throw new Error(
    'Usage: node --experimental-strip-types scripts/run_selected_image_crop_directories.mjs <parent> <from-index> <through-index>',
  );
}
const parent = path.resolve(parentArg);
const fromIndex = parsePositiveInteger(fromArg, 'from-index');
const throughIndex = parsePositiveInteger(throughArg, 'through-index');
if (throughIndex < fromIndex) throw new Error('CROP_RUN_INDEX_RANGE_INVALID');

const sourceDirectories = (await fs.readdir(parent, { withFileTypes: true }))
  .filter((entry) => entry.isDirectory() && !entry.name.endsWith(' cut'))
  .map((entry) => ({ name: entry.name, start: numericPrefix(entry.name) }))
  .filter((entry) => entry.start !== null)
  .sort(
    (left, right) =>
      left.start - right.start || left.name.localeCompare(right.name),
  );

const selected = sourceDirectories.slice(fromIndex - 1, throughIndex);
if (selected.length !== throughIndex - fromIndex + 1) {
  throw new Error('CROP_RUN_DIRECTORY_RANGE_INCOMPLETE');
}

for (let offset = 0; offset < selected.length; offset += 1) {
  const directoryIndex = fromIndex + offset;
  const source = selected[offset];
  await processDirectory(directoryIndex, source.name);
}

async function processDirectory(directoryIndex, sourceName) {
  const sourcePath = path.join(parent, sourceName);
  const outputName = `${sourceName} cut`;
  const outputPath = path.join(parent, outputName);
  const statePath = path.join(outputPath, '.crop-run-state');
  const manifestPath = path.join(
    outputPath,
    'manual-image-crop-output-v1.json',
  );
  await fs.mkdir(outputPath, { recursive: true });

  const files = await sourceInventory(sourcePath);
  const inventoryChecksum = sha256(
    Buffer.from(
      JSON.stringify(
        files.map(({ fileName, sizeBytes, lastModifiedMs }) => ({
          fileName,
          sizeBytes,
          lastModifiedMs,
        })),
      ),
    ),
  );
  const existingManifest = await readJsonOrNull(manifestPath);
  if (existingManifest !== null) {
    if (
      existingManifest.sourceInventoryChecksumSha256 === inventoryChecksum &&
      existingManifest.entries?.every(
        (entry) =>
          entry.result?.autoCropProposal?.policyVersion ===
          SELECTED_IMAGE_AUTO_CROP_POLICY,
      )
    ) {
      console.log(`[${directoryIndex}] ${sourceName}: already complete`);
      return;
    }
    throw new Error(`CROP_RUN_OUTPUT_ALREADY_OWNED:${outputPath}`);
  }
  await fs.mkdir(statePath, { recursive: true });
  const metaPath = path.join(statePath, 'meta.json');
  const existingMeta = await readJsonOrNull(metaPath);
  const expectedMeta = {
    schemaVersion: 1,
    sourceDirectoryName: sourceName,
    outputDirectoryName: outputName,
    sourceInventoryChecksumSha256: inventoryChecksum,
    policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
    entryCount: files.length,
  };
  if (existingMeta === null) await writeJsonAtomic(metaPath, expectedMeta);
  else if (JSON.stringify(existingMeta) !== JSON.stringify(expectedMeta)) {
    throw new Error(`CROP_RUN_STATE_MISMATCH:${outputPath}`);
  }

  const results = new Array(files.length).fill(null);
  for (
    let shardIndex = 0;
    shardIndex < Math.ceil(files.length / 64);
    shardIndex += 1
  ) {
    const shard = await readJsonOrNull(shardPath(statePath, shardIndex));
    if (shard === null) continue;
    for (const item of shard.items ?? []) results[item.index] = item.result;
  }
  console.log(
    `[${directoryIndex}] ${sourceName}: ${results.filter(Boolean).length}/${files.length}`,
  );

  for (let index = 0; index < files.length; index += 1) {
    if (results[index] !== null) continue;
    const sourceFile = files[index];
    const sourceFilePath = path.join(sourcePath, sourceFile.fileName);
    const outputFilePath = path.join(outputPath, sourceFile.fileName);
    if (await exists(outputFilePath)) {
      throw new Error(`CROP_RUN_UNTRACKED_OUTPUT:${outputFilePath}`);
    }
    const sourceBytes = await fs.readFile(sourceFilePath);
    const sourceChecksumSha256 = sha256(sourceBytes);
    const decoded = await sharp(sourceBytes)
      .rotate()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const sample = await sharp(decoded.data, { raw: decoded.info })
      .resize({
        width: Math.min(
          SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH,
          decoded.info.width,
        ),
      })
      .ensureAlpha()
      .raw()
      .toBuffer({ resolveWithObject: true });
    const proposal = detectSelectedImageCropBand(
      {
        width: sample.info.width,
        height: sample.info.height,
        rgba: new Uint8ClampedArray(sample.data),
      },
      { width: decoded.info.width, height: decoded.info.height },
    );
    const outputBytes = await sharp(decoded.data, { raw: decoded.info })
      .extract({
        left: 0,
        top: proposal.crop.topY,
        width: proposal.crop.width,
        height: proposal.crop.bottomY - proposal.crop.topY,
      })
      .jpeg({ quality: 98 })
      .toBuffer();
    const outputChecksumSha256 = sha256(outputBytes);
    const partPath = `${outputFilePath}.part`;
    await fs.writeFile(partPath, outputBytes, { flag: 'wx' });
    await fs.rename(partPath, outputFilePath);
    results[index] = {
      status: 'accepted',
      crop: proposal.crop,
      sourceChecksumSha256,
      outputChecksumSha256,
      acceptedAt: new Date().toISOString(),
      autoCropProposal: proposal,
    };
    await writeResultShard(statePath, results, Math.floor(index / 64));
    if ((index + 1) % 25 === 0 || index + 1 === files.length) {
      console.log(
        `[${directoryIndex}] ${sourceName}: ${index + 1}/${files.length}`,
      );
    }
  }

  const now = new Date().toISOString();
  const manifest = {
    schemaVersion: 1,
    rendererVersion: 'manual-selected-image-band-crop-jpeg-v1',
    sourceDirectoryName: sourceName,
    outputDirectoryName: outputName,
    sourceInventoryChecksumSha256: inventoryChecksum,
    revision: files.length,
    currentIndex: Math.max(0, files.length - 1),
    entries: files.map((entry, index) => ({
      ...entry,
      result: results[index],
    })),
    reviewedFileNames: [],
    pendingOperation: null,
    updatedAt: now,
  };
  await writeJsonAtomic(manifestPath, manifest);
  await fs.rm(statePath, { recursive: true, force: false });
  console.log(
    `[${directoryIndex}] ${sourceName}: complete ${files.length}/${files.length}`,
  );
}

async function sourceInventory(directory) {
  const entries = await fs.readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    if (!entry.isFile() || !/\.jpe?g$/iu.test(entry.name)) continue;
    const match = /^seq_(\d+)-(\d+)\.jpe?g$/iu.exec(entry.name);
    if (!match) throw new Error(`CROP_RUN_SOURCE_NAME_INVALID:${entry.name}`);
    const rangeStart = Number(match[1]);
    const rangeEnd = Number(match[2]);
    if (
      rangeStart < 1 ||
      rangeEnd < rangeStart ||
      rangeEnd - rangeStart + 1 > 9
    ) {
      throw new Error(`CROP_RUN_SOURCE_RANGE_INVALID:${entry.name}`);
    }
    const stats = await fs.stat(path.join(directory, entry.name));
    files.push({
      fileName: entry.name,
      sizeBytes: stats.size,
      lastModifiedMs: Math.trunc(stats.mtimeMs),
      rangeStart,
      rangeEnd,
    });
  }
  files.sort(
    (left, right) =>
      left.rangeStart - right.rangeStart || left.rangeEnd - right.rangeEnd,
  );
  for (let index = 1; index < files.length; index += 1) {
    if (files[index].rangeStart <= files[index - 1].rangeEnd) {
      throw new Error(`CROP_RUN_SOURCE_OVERLAP:${files[index].fileName}`);
    }
  }
  if (files.length === 0) throw new Error(`CROP_RUN_SOURCE_EMPTY:${directory}`);
  return files;
}

async function writeResultShard(statePath, results, shardIndex) {
  const start = shardIndex * 64;
  const items = [];
  for (
    let index = start;
    index < Math.min(results.length, start + 64);
    index += 1
  ) {
    if (results[index] !== null) items.push({ index, result: results[index] });
  }
  await writeJsonAtomic(shardPath(statePath, shardIndex), {
    schemaVersion: 1,
    items,
  });
}

function shardPath(statePath, shardIndex) {
  return path.join(
    statePath,
    `results-${String(shardIndex).padStart(5, '0')}.json`,
  );
}

async function writeJsonAtomic(target, value) {
  const temporary = `${target}.tmp`;
  await fs.writeFile(temporary, JSON.stringify(value), { flag: 'w' });
  await fs.rename(temporary, target);
}

async function readJsonOrNull(target) {
  try {
    return JSON.parse(await fs.readFile(target, 'utf8'));
  } catch (cause) {
    if (cause?.code === 'ENOENT') return null;
    throw cause;
  }
}

async function exists(target) {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
}

function sha256(value) {
  return createHash('sha256').update(value).digest('hex');
}

function numericPrefix(value) {
  const match = /^\s*(\d+)/u.exec(value);
  return match ? Number(match[1]) : null;
}

function parsePositiveInteger(value, label) {
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 1)
    throw new Error(`CROP_RUN_${label.toUpperCase()}_INVALID`);
  return parsed;
}
