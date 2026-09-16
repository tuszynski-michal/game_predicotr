import { createHash } from 'node:crypto';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import sharp from 'sharp';

import {
  SELECTED_IMAGE_CROP_MAXIMUM_HEIGHT_RATIO,
  selectedImageCropAutomaticCorrectionRecalculationFileNames,
  selectedImageCropReviewReason,
} from '../packages/manual-image-selection-core/src/crop-session.ts';
import { CROP_V11_POLICY } from '../packages/manual-image-selection-core/src/auto-crop-v11.ts';
import {
  CROP_V12_FINGERPRINT,
  CROP_V12_POLICY,
  fourPointAnchorFromStructuralEvidence,
} from '../packages/manual-image-selection-core/src/auto-crop-v12-registration.ts';
import {
  renderCropSource,
  sha256,
} from './lib/selected-crop-durable-runner.mjs';

const STATE_DIRECTORY = '.selected-crop-v12-correction-preview';
const REPORT_NAME = 'selected-crop-v12-correction-preview-report.json';
const INDEX_NAME = 'selected-crop-v12-correction-preview.html';
const RESULT_SHARD_SIZE = 32;
const MAX_ANCHOR_DISTANCE = 48;
const MAX_ANCHOR_ATTEMPTS = 3;

async function exists(file) {
  try {
    await fs.lstat(file);
    return true;
  } catch (cause) {
    if (cause.code === 'ENOENT') return false;
    throw cause;
  }
}

async function safe(file, directory = false) {
  const info = await fs.lstat(file);
  if (
    info.isSymbolicLink() ||
    (directory ? !info.isDirectory() : !info.isFile())
  )
    throw new Error(`CROP_PREVIEW_PATH_UNSAFE:${file}`);
  if (
    (await fs.realpath(file)).toLowerCase() !== path.resolve(file).toLowerCase()
  )
    throw new Error(`CROP_PREVIEW_PATH_UNSAFE:${file}`);
  return info;
}

async function atomicJson(file, value) {
  const part = `${file}.part`;
  if (await exists(part)) {
    await safe(part);
    await fs.unlink(part);
  }
  if (await exists(file)) await safe(file);
  const handle = await fs.open(part, 'wx');
  try {
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`);
    await handle.sync();
  } finally {
    await handle.close();
  }
  await fs.rename(part, file);
}

async function readJson(file) {
  return JSON.parse(await fs.readFile(file, 'utf8'));
}

export function orderedNeighbourIndexes(targetIndex, length, radius) {
  if (
    !Number.isInteger(targetIndex) ||
    !Number.isInteger(length) ||
    !Number.isInteger(radius) ||
    targetIndex < 0 ||
    targetIndex >= length ||
    length < 1 ||
    radius < 1
  )
    throw new Error('CROP_PREVIEW_NEIGHBOUR_RANGE_INVALID');
  const result = [];
  for (let distance = 1; distance <= radius; distance += 1) {
    const before = targetIndex - distance;
    const after = targetIndex + distance;
    if (before >= 0) result.push(before);
    if (after < length) result.push(after);
  }
  return result;
}

async function inputStateChecksum(stateDirectory) {
  const files = (await fs.readdir(stateDirectory, { withFileTypes: true }))
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => entry.name)
    .sort();
  const resultDirectory = path.join(stateDirectory, 'results');
  const resultFiles = (
    await fs.readdir(resultDirectory, { withFileTypes: true })
  )
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => entry.name)
    .sort();
  const hash = createHash('sha256');
  for (const name of files) {
    hash.update(name);
    hash.update(await fs.readFile(path.join(stateDirectory, name)));
  }
  for (const name of resultFiles) {
    hash.update(name);
    hash.update(await fs.readFile(path.join(resultDirectory, name)));
  }
  return hash.digest('hex');
}

async function loadInput(source, currentOutput) {
  const stateDirectory = path.join(currentOutput, '.manual-image-crop-state');
  await safe(source, true);
  await safe(currentOutput, true);
  await safe(stateDirectory, true);
  const inventory = await readJson(
    path.join(stateDirectory, 'inventory-v2.json'),
  );
  const review = await readJson(path.join(stateDirectory, 'review-v2.json'));
  const session = await readJson(path.join(stateDirectory, 'session-v2.json'));
  const resultDirectory = path.join(stateDirectory, 'results');
  const shardNames = (await fs.readdir(resultDirectory))
    .filter((name) => /^\d{6}\.json$/.test(name))
    .sort();
  const shards = await Promise.all(
    shardNames.map((name) => readJson(path.join(resultDirectory, name))),
  );
  const snapshot = { inventory, review, session, shards };
  if (
    inventory.sourceDirectoryName !== path.basename(source) ||
    inventory.outputDirectoryName !== path.basename(currentOutput)
  )
    throw new Error('CROP_PREVIEW_INPUT_IDENTITY_MISMATCH');
  const sourceResults = new Map(
    shards.flatMap((shard) => Object.entries(shard.results)),
  );
  const correctionNames = [
    ...selectedImageCropAutomaticCorrectionRecalculationFileNames(snapshot),
  ];
  return {
    snapshot,
    correctionNames,
    sourceResults,
    stateDirectory,
    stateChecksum: await inputStateChecksum(stateDirectory),
  };
}

function selectedCropFailureRecoveryFileNames(snapshot, sourceResults) {
  if (!Array.isArray(snapshot.session.failures))
    throw new Error('CROP_PREVIEW_FAILURE_LIST_INVALID');
  const inventoryNames = snapshot.inventory.entries.map(
    (entry) => entry.fileName,
  );
  const inventorySet = new Set(inventoryNames);
  const selected = new Set();
  for (const failure of snapshot.session.failures) {
    const fileName = failure?.fileName;
    if (
      typeof fileName !== 'string' ||
      !inventorySet.has(fileName) ||
      sourceResults.has(fileName) ||
      selected.has(fileName)
    )
      throw new Error('CROP_PREVIEW_FAILURE_LIST_INVALID');
    selected.add(fileName);
  }
  return inventoryNames.filter((fileName) => selected.has(fileName));
}

async function selectedCropExcessiveHeightFileNames(
  snapshot,
  sourceResults,
  currentOutput,
) {
  const selected = [];
  for (const entry of snapshot.inventory.entries) {
    const result = sourceResults.get(entry.fileName);
    if (result === undefined) continue;
    const sourceDimensions = result.crop;
    if (
      sourceDimensions === null ||
      typeof sourceDimensions !== 'object' ||
      !Number.isInteger(sourceDimensions.width) ||
      !Number.isInteger(sourceDimensions.height) ||
      sourceDimensions.width < 1 ||
      sourceDimensions.height < 1
    )
      throw new Error('CROP_PREVIEW_RESULT_DIMENSIONS_INVALID');
    const outputFile = path.join(currentOutput, entry.fileName);
    await safe(outputFile);
    const metadata = await sharp(outputFile).metadata();
    if (
      !Number.isInteger(metadata.width) ||
      !Number.isInteger(metadata.height) ||
      metadata.width !== sourceDimensions.width ||
      metadata.height < 1 ||
      metadata.height > sourceDimensions.height
    )
      throw new Error('CROP_PREVIEW_OUTPUT_DIMENSIONS_INVALID');
    if (
      metadata.height / sourceDimensions.height >
      SELECTED_IMAGE_CROP_MAXIMUM_HEIGHT_RATIO
    )
      selected.push(entry.fileName);
  }
  return selected;
}

function shardName(index) {
  return `${String(Math.floor(index / RESULT_SHARD_SIZE)).padStart(6, '0')}.json`;
}

async function loadPreviewResults(resultsDirectory) {
  const results = new Map();
  if (!(await exists(resultsDirectory))) return results;
  await safe(resultsDirectory, true);
  for (const name of (await fs.readdir(resultsDirectory)).sort()) {
    if (!/^\d{6}\.json$/.test(name)) continue;
    const shard = await readJson(path.join(resultsDirectory, name));
    for (const [fileName, result] of Object.entries(shard.results ?? {}))
      results.set(fileName, result);
  }
  return results;
}

async function savePreviewShard(
  resultsDirectory,
  correctionNames,
  results,
  index,
) {
  const first = Math.floor(index / RESULT_SHARD_SIZE) * RESULT_SHARD_SIZE;
  const names = correctionNames.slice(first, first + RESULT_SHARD_SIZE);
  await atomicJson(path.join(resultsDirectory, shardName(index)), {
    schemaVersion: 1,
    shardIndex: Math.floor(index / RESULT_SHARD_SIZE),
    results: Object.fromEntries(
      names
        .filter((name) => results.has(name))
        .map((name) => [name, results.get(name)]),
    ),
  });
}

async function verifySavedResult(sourceFile, outputFile, result) {
  await safe(sourceFile);
  await safe(outputFile);
  if (sha256(await fs.readFile(sourceFile)) !== result.sourceChecksumSha256)
    throw new Error('CROP_PREVIEW_SOURCE_CHANGED');
  if (sha256(await fs.readFile(outputFile)) !== result.outputChecksumSha256)
    throw new Error('CROP_PREVIEW_OUTPUT_CHANGED');
}

function resultMethod(proposal) {
  if (proposal.registration?.status === 'registered') return 'registered';
  if (proposal.structural?.status === 'detected') return 'structural';
  return 'manual';
}

function htmlEscape(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

async function writeReviewIndex(output, report) {
  const cards = report.observations
    .map(
      (item) => `<article class="${htmlEscape(item.method)}">
  <a href="${encodeURIComponent(item.fileName)}"><img loading="lazy" src="${encodeURIComponent(item.fileName)}" alt="${htmlEscape(item.fileName)}"></a>
  <strong>${htmlEscape(item.fileName)}</strong>
  <span>${htmlEscape(item.method)} · ${item.topY}–${item.bottomY}</span>
  ${item.structuralReason ? `<small>${htmlEscape(item.structuralReason)}</small>` : ''}
  ${item.reason ? `<small>${htmlEscape(item.reason)}</small>` : ''}
</article>`,
    )
    .join('\n');
  const html = `<!doctype html><html lang="pl"><meta charset="utf-8"><title>Podgląd korekt cropów v12</title>
<style>body{font-family:Segoe UI,sans-serif;background:#0b1020;color:#f8fafc;margin:20px}header{position:sticky;top:0;background:#0b1020;padding:8px 0;z-index:2}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}article{border:3px solid #166534;background:#111827;padding:8px;display:grid;gap:6px}article.manual{border-color:#b91c1c}img{width:100%;height:260px;object-fit:contain;background:#030712}span,small{color:#cbd5e1;font-size:12px}</style>
<body><header><h1>Podgląd korekt cropów v12</h1><p>${report.completed}/${report.total} · automatyczne ${report.automatic} · nadal ręczne ${report.manual} · błędy ${report.failures.length}</p></header><main class="grid">${cards}</main></body></html>`;
  await fs.writeFile(path.join(output, INDEX_NAME), html);
}

async function runSelectedCropPreview(
  sourceArgument,
  currentOutputArgument,
  previewOutputArgument,
  { onProgress = () => {}, selection = 'automatic_corrections' } = {},
) {
  const source = path.resolve(sourceArgument);
  const currentOutput = path.resolve(currentOutputArgument);
  const output = path.resolve(previewOutputArgument);
  if (
    new Set([
      source.toLowerCase(),
      currentOutput.toLowerCase(),
      output.toLowerCase(),
    ]).size !== 3
  )
    throw new Error('CROP_PREVIEW_PATHS_MUST_BE_DISTINCT');
  const input = await loadInput(source, currentOutput);
  const candidateNames =
    selection === 'automatic_corrections'
      ? input.correctionNames
      : selection === 'missing_failures'
        ? selectedCropFailureRecoveryFileNames(
            input.snapshot,
            input.sourceResults,
          )
        : selection === 'excessive_height'
          ? await selectedCropExcessiveHeightFileNames(
              input.snapshot,
              input.sourceResults,
              currentOutput,
            )
          : (() => {
              throw new Error('CROP_PREVIEW_SELECTION_INVALID');
            })();
  if (new Set(candidateNames).size !== candidateNames.length)
    throw new Error('CROP_PREVIEW_CORRECTION_LIST_INVALID');
  if (candidateNames.length === 0)
    throw new Error(
      selection === 'missing_failures'
        ? 'CROP_PREVIEW_FAILURE_LIST_EMPTY'
        : selection === 'excessive_height'
          ? 'CROP_PREVIEW_EXCESSIVE_HEIGHT_LIST_EMPTY'
          : 'CROP_PREVIEW_CORRECTION_LIST_INVALID',
    );
  const candidateHash = sha256(Buffer.from(JSON.stringify(candidateNames)));
  if (!(await exists(output))) await fs.mkdir(output);
  await safe(output, true);
  const state = path.join(output, STATE_DIRECTORY);
  if (!(await exists(state))) await fs.mkdir(state);
  await safe(state, true);
  const resultsDirectory = path.join(state, 'results');
  if (!(await exists(resultsDirectory))) await fs.mkdir(resultsDirectory);
  const meta = {
    schemaVersion: 1,
    policy: CROP_V12_POLICY,
    fingerprint: CROP_V12_FINGERPRINT,
    sourceDirectory: source,
    currentOutputDirectory: currentOutput,
    previewOutputDirectory: output,
    inputStateChecksumSha256: input.stateChecksum,
    ...(selection === 'automatic_corrections'
      ? {
          correctionListChecksumSha256: candidateHash,
          correctionCount: candidateNames.length,
        }
      : selection === 'missing_failures'
        ? {
            selection,
            failureListChecksumSha256: candidateHash,
            failureCount: candidateNames.length,
          }
        : {
            selection,
            excessiveHeightListChecksumSha256: candidateHash,
            excessiveHeightCount: candidateNames.length,
            maximumCropHeightRatio: SELECTED_IMAGE_CROP_MAXIMUM_HEIGHT_RATIO,
          }),
    maximumAnchorDistance: MAX_ANCHOR_DISTANCE,
    maximumAnchorAttempts: MAX_ANCHOR_ATTEMPTS,
  };
  const metaFile = path.join(state, 'meta.json');
  if (await exists(metaFile)) {
    if (JSON.stringify(await readJson(metaFile)) !== JSON.stringify(meta))
      throw new Error('CROP_PREVIEW_INPUT_OR_POLICY_CHANGED');
  } else await atomicJson(metaFile, meta);
  const allowed = new Set([
    STATE_DIRECTORY,
    REPORT_NAME,
    INDEX_NAME,
    ...candidateNames,
  ]);
  if ((await fs.readdir(output)).some((name) => !allowed.has(name)))
    throw new Error('CROP_PREVIEW_OUTPUT_FOREIGN');

  const results = await loadPreviewResults(resultsDirectory);
  const pendingFile = path.join(state, 'pending.json');
  const partFile = path.join(state, 'output.part');
  if (await exists(pendingFile)) {
    const pending = await readJson(pendingFile);
    const index = candidateNames.indexOf(pending.fileName);
    if (index < 0) throw new Error('CROP_PREVIEW_PENDING_FOREIGN');
    const target = path.join(output, pending.fileName);
    if (await exists(target)) {
      await verifySavedResult(
        path.join(source, pending.fileName),
        target,
        pending.result,
      );
      results.set(pending.fileName, pending.result);
      await savePreviewShard(resultsDirectory, candidateNames, results, index);
    }
    if (await exists(partFile)) {
      await safe(partFile);
      await fs.unlink(partFile);
    }
    await fs.unlink(pendingFile);
  } else if (await exists(partFile)) {
    throw new Error('CROP_PREVIEW_PART_WITHOUT_INTENT');
  }

  const inventoryNames = input.snapshot.inventory.entries.map(
    (entry) => entry.fileName,
  );
  const inventoryEntries = new Map(
    input.snapshot.inventory.entries.map((entry) => [entry.fileName, entry]),
  );
  const inventoryIndex = new Map(
    inventoryNames.map((name, index) => [name, index]),
  );
  const structuralCache = new Map();
  const anchors = new Map();

  async function inspectAnchor(candidateName) {
    if (structuralCache.has(candidateName))
      return structuralCache.get(candidateName);
    const bytes = await fs.readFile(path.join(source, candidateName));
    const sourceResult = input.sourceResults.get(candidateName);
    if (
      sourceResult?.sourceChecksumSha256 &&
      sha256(bytes) !== sourceResult.sourceChecksumSha256
    )
      throw new Error(`CROP_PREVIEW_SOURCE_CHANGED:${candidateName}`);
    const rendered = await renderCropSource(bytes, CROP_V11_POLICY);
    const anchorable =
      rendered.proposal.structural?.status === 'detected' &&
      rendered.proposal.structural.labels.length === 9;
    structuralCache.set(candidateName, anchorable);
    if (anchorable) {
      anchors.set(candidateName, {
        bytes,
        descriptor: fourPointAnchorFromStructuralEvidence({
          sourceName: candidateName,
          sourceChecksumSha256: sha256(bytes),
          evidence: rendered.proposal.structural,
        }),
      });
    }
    return anchorable;
  }

  async function nearestAnchors(fileName) {
    const targetIndex = inventoryIndex.get(fileName);
    if (targetIndex === undefined)
      throw new Error('CROP_PREVIEW_SOURCE_NOT_IN_INVENTORY');
    const candidates = [];
    for (const [name, anchor] of anchors) {
      const index = inventoryIndex.get(name);
      const distance = Math.abs(index - targetIndex);
      if (distance > 0 && distance <= MAX_ANCHOR_DISTANCE)
        candidates.push({ anchor, distance, index });
    }
    candidates.sort((a, b) => a.distance - b.distance || a.index - b.index);
    if (candidates.length < MAX_ANCHOR_ATTEMPTS) {
      for (const index of orderedNeighbourIndexes(
        targetIndex,
        inventoryNames.length,
        MAX_ANCHOR_DISTANCE,
      )) {
        const name = inventoryNames[index];
        if (name === fileName || anchors.has(name)) continue;
        if (!(await inspectAnchor(name))) continue;
        candidates.push({
          anchor: anchors.get(name),
          distance: Math.abs(index - targetIndex),
          index,
        });
        candidates.sort((a, b) => a.distance - b.distance || a.index - b.index);
        if (candidates.length >= MAX_ANCHOR_ATTEMPTS) break;
      }
    }
    return candidates.slice(0, MAX_ANCHOR_ATTEMPTS).map((item) => item.anchor);
  }

  const failures = [];
  for (let index = 0; index < candidateNames.length; index += 1) {
    const fileName = candidateNames[index];
    const sourceFile = path.join(source, fileName);
    const target = path.join(output, fileName);
    if (results.has(fileName)) {
      await verifySavedResult(sourceFile, target, results.get(fileName));
      onProgress({
        completed: results.size,
        total: candidateNames.length,
        fileName,
      });
      continue;
    }
    if (await exists(target))
      throw new Error(`CROP_PREVIEW_OUTPUT_UNTRACKED:${fileName}`);
    try {
      const startedAt = Date.now();
      const inventoryEntry = inventoryEntries.get(fileName);
      if (inventoryEntry === undefined)
        throw new Error('CROP_PREVIEW_SOURCE_NOT_IN_INVENTORY');
      if (selection === 'missing_failures') {
        const sourceInfo = await safe(sourceFile);
        if (
          sourceInfo.size !== inventoryEntry.sizeBytes ||
          Math.trunc(sourceInfo.mtimeMs) !== inventoryEntry.lastModifiedMs
        )
          throw new Error('CROP_PREVIEW_SOURCE_CHANGED');
      }
      const bytes = await fs.readFile(sourceFile);
      const previous = input.sourceResults.get(fileName);
      const sourceChecksumSha256 = sha256(bytes);
      if (
        previous?.sourceChecksumSha256 !== undefined &&
        previous.sourceChecksumSha256 !== sourceChecksumSha256
      )
        throw new Error('CROP_PREVIEW_SOURCE_CHANGED');
      let rendered = await renderCropSource(bytes, CROP_V12_POLICY, null);
      if (rendered.proposal.structural?.status === 'detected') {
        const anchorable = rendered.proposal.structural.labels.length === 9;
        if (anchorable)
          anchors.set(fileName, {
            bytes,
            descriptor: fourPointAnchorFromStructuralEvidence({
              sourceName: fileName,
              sourceChecksumSha256,
              evidence: rendered.proposal.structural,
            }),
          });
        structuralCache.set(fileName, anchorable);
      } else {
        structuralCache.set(fileName, false);
        for (const anchor of await nearestAnchors(fileName)) {
          const attempt = await renderCropSource(
            bytes,
            CROP_V12_POLICY,
            anchor,
          );
          if (attempt.proposal.registration?.status !== 'registered') continue;
          rendered = attempt;
          break;
        }
      }
      if (Date.now() - startedAt > 120_000)
        throw new Error('CROP_PREVIEW_FILE_TIMEOUT');
      const result = {
        schemaVersion: 1,
        fileName,
        sourceChecksumSha256,
        outputChecksumSha256: sha256(rendered.output),
        policy: CROP_V12_POLICY,
        fingerprint: CROP_V12_FINGERPRINT,
        method: resultMethod(rendered.proposal),
        reviewReason: selectedImageCropReviewReason(rendered.proposal),
        crop: rendered.proposal.crop,
        proposal: rendered.proposal,
        completedAt: new Date().toISOString(),
      };
      const free = await fs.statfs(output);
      if (
        free.bavail * free.bsize <
        5 * 1024 ** 3 + rendered.output.length * 1.2
      )
        throw new Error('CROP_PREVIEW_STORAGE_CAPACITY_INSUFFICIENT');
      await atomicJson(pendingFile, { fileName, result });
      const outputHandle = await fs.open(partFile, 'wx');
      try {
        await outputHandle.writeFile(rendered.output);
        await outputHandle.sync();
      } finally {
        await outputHandle.close();
      }
      // The preview directory can live on a volume that does not support hard
      // links. The target was checked absent and this runner owns the output
      // directory, so same-volume rename publishes the fsynced file atomically.
      await fs.rename(partFile, target);
      await verifySavedResult(sourceFile, target, result);
      results.set(fileName, result);
      await savePreviewShard(resultsDirectory, candidateNames, results, index);
      await fs.unlink(pendingFile);
    } catch (cause) {
      if (await exists(pendingFile)) throw cause;
      failures.push({
        fileName,
        code:
          cause instanceof Error ? cause.message : 'CROP_PREVIEW_UNKNOWN_ERROR',
      });
    }
    onProgress({
      completed: results.size,
      total: candidateNames.length,
      fileName,
    });
  }
  if ((await inputStateChecksum(input.stateDirectory)) !== input.stateChecksum)
    throw new Error('CROP_PREVIEW_INPUT_STATE_CHANGED_DURING_RUN');
  const observations = candidateNames.flatMap((fileName) => {
    const result = results.get(fileName);
    return result
      ? [
          {
            fileName,
            method: result.method,
            reason: result.reviewReason,
            structuralReason: result.proposal.structural?.reason ?? null,
            topY: result.crop.topY,
            bottomY: result.crop.bottomY,
            height: result.crop.height,
            sourceChecksumSha256: result.sourceChecksumSha256,
            outputChecksumSha256: result.outputChecksumSha256,
            anchorSourceName:
              result.proposal.registration?.anchorSourceName ?? null,
          },
        ]
      : [];
  });
  const report = {
    schemaVersion: 1,
    policy: CROP_V12_POLICY,
    fingerprint: CROP_V12_FINGERPRINT,
    inputStateChecksumSha256: input.stateChecksum,
    selection,
    candidateListChecksumSha256: candidateHash,
    total: candidateNames.length,
    completed: observations.length,
    automatic: observations.filter((item) => item.reason === null).length,
    structural: observations.filter((item) => item.method === 'structural')
      .length,
    registered: observations.filter((item) => item.method === 'registered')
      .length,
    boardBuffered: observations.filter(
      (item) => item.structuralReason === 'complete_layout_board_buffer',
    ).length,
    manual: observations.filter((item) => item.reason !== null).length,
    failures,
    observations,
    completedAt: new Date().toISOString(),
  };
  await atomicJson(path.join(output, REPORT_NAME), report);
  await writeReviewIndex(output, report);
  return report;
}

export async function runSelectedCropCorrectionPreview(
  sourceArgument,
  currentOutputArgument,
  previewOutputArgument,
  options = {},
) {
  return runSelectedCropPreview(
    sourceArgument,
    currentOutputArgument,
    previewOutputArgument,
    options,
  );
}

export async function runSelectedCropFailureRecoveryPreview(
  sourceArgument,
  currentOutputArgument,
  previewOutputArgument,
  { onProgress = () => {} } = {},
) {
  return runSelectedCropPreview(
    sourceArgument,
    currentOutputArgument,
    previewOutputArgument,
    { onProgress, selection: 'missing_failures' },
  );
}

export async function runSelectedCropExcessiveHeightPreview(
  sourceArgument,
  currentOutputArgument,
  previewOutputArgument,
  { onProgress = () => {} } = {},
) {
  return runSelectedCropPreview(
    sourceArgument,
    currentOutputArgument,
    previewOutputArgument,
    { onProgress, selection: 'excessive_height' },
  );
}

async function main() {
  const [source, currentOutput, previewOutput, mode] = process.argv.slice(2);
  if (!source || !currentOutput || !previewOutput)
    throw new Error(
      'Usage: <source-directory> <current-cut-directory> <preview-output-directory> [--missing-failures|--too-tall]',
    );
  if (
    mode !== undefined &&
    mode !== '--missing-failures' &&
    mode !== '--too-tall'
  )
    throw new Error('CROP_PREVIEW_MODE_INVALID');
  const runPreview =
    mode === '--missing-failures'
      ? runSelectedCropFailureRecoveryPreview
      : mode === '--too-tall'
        ? runSelectedCropExcessiveHeightPreview
        : runSelectedCropCorrectionPreview;
  const report = await runPreview(source, currentOutput, previewOutput, {
    onProgress: (progress) => {
      if (
        progress.completed % 10 === 0 ||
        progress.completed === progress.total
      )
        process.stdout.write(`${JSON.stringify(progress)}\n`);
    },
  });
  process.stdout.write(
    `${JSON.stringify({
      total: report.total,
      completed: report.completed,
      automatic: report.automatic,
      structural: report.structural,
      registered: report.registered,
      boardBuffered: report.boardBuffered,
      manual: report.manual,
      failures: report.failures.length,
    })}\n`,
  );
  if (report.failures.length > 0) process.exitCode = 1;
}

if (
  process.argv[1] &&
  pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url
)
  await main();
