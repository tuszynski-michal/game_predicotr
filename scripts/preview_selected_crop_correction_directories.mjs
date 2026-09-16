import { promises as fs } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import {
  effectiveSelectedImageCropCorrections,
  selectedImageCropAutomaticCorrectionRecalculationFileNames,
} from '../packages/manual-image-selection-core/src/crop-session.ts';
import { CROP_V12_FINGERPRINT } from '../packages/manual-image-selection-core/src/auto-crop-v12-registration.ts';
import { runSelectedCropCorrectionPreview } from './preview_selected_crop_corrections.mjs';

const CUT_SUFFIX = ' cut';
const PREVIEW_SUFFIX = ' v12 board-buffer preview';
const BATCH_REPORT_NAME = 'selected-crop-v12-board-buffer-batch-report.json';
const natural = new Intl.Collator('pl', {
  numeric: true,
  sensitivity: 'base',
});

async function exists(target) {
  try {
    await fs.lstat(target);
    return true;
  } catch (cause) {
    if (cause.code === 'ENOENT') return false;
    throw cause;
  }
}

async function safeDirectory(target) {
  const info = await fs.lstat(target);
  if (!info.isDirectory() || info.isSymbolicLink())
    throw new Error(`CROP_BATCH_PATH_UNSAFE:${target}`);
  if (
    (await fs.realpath(target)).toLowerCase() !==
    path.resolve(target).toLowerCase()
  )
    throw new Error(`CROP_BATCH_PATH_UNSAFE:${target}`);
}

async function readJson(file) {
  const info = await fs.lstat(file);
  if (!info.isFile() || info.isSymbolicLink())
    throw new Error(`CROP_BATCH_STATE_UNSAFE:${file}`);
  return JSON.parse(await fs.readFile(file, 'utf8'));
}

async function readSnapshot(cutDirectory) {
  const stateDirectory = path.join(cutDirectory, '.manual-image-crop-state');
  await safeDirectory(stateDirectory);
  const [inventory, session, review] = await Promise.all([
    readJson(path.join(stateDirectory, 'inventory-v2.json')),
    readJson(path.join(stateDirectory, 'session-v2.json')),
    readJson(path.join(stateDirectory, 'review-v2.json')),
  ]);
  const resultsDirectory = path.join(stateDirectory, 'results');
  await safeDirectory(resultsDirectory);
  const shardNames = (await fs.readdir(resultsDirectory))
    .filter((name) => /^\d{6}\.json$/.test(name))
    .sort();
  const shards = await Promise.all(
    shardNames.map((name) => readJson(path.join(resultsDirectory, name))),
  );
  if (
    inventory?.schemaVersion !== 2 ||
    !Array.isArray(inventory.entries) ||
    session?.schemaVersion !== 2 ||
    !Array.isArray(session.failures) ||
    review?.schemaVersion !== 2 ||
    !Array.isArray(review.reviewedFileNames) ||
    !Array.isArray(review.correctionFileNames) ||
    !Array.isArray(review.correctedFileNames) ||
    shards.some(
      (shard) =>
        shard?.schemaVersion !== 2 ||
        typeof shard.results !== 'object' ||
        shard.results === null,
    )
  )
    throw new Error('CROP_BATCH_STATE_INVALID');
  return { inventory, session, review, shards };
}

function classifySnapshot(snapshot, cutName, sourceAvailable) {
  const inventoryNames = snapshot.inventory.entries.map(
    (entry) => entry.fileName,
  );
  const inventorySet = new Set(inventoryNames);
  const resultNames = snapshot.shards.flatMap((shard) =>
    Object.keys(shard.results),
  );
  const resultSet = new Set(resultNames);
  const missingResults = inventoryNames.filter(
    (name) => !resultSet.has(name),
  ).length;
  const foreignResults = [...resultSet].filter(
    (name) => !inventorySet.has(name),
  ).length;
  const duplicateResults = resultNames.length - resultSet.size;
  const automaticCorrections = [
    ...selectedImageCropAutomaticCorrectionRecalculationFileNames(snapshot),
  ];
  const effectiveCorrections = [
    ...effectiveSelectedImageCropCorrections(snapshot),
  ];
  const base = {
    cutName,
    sourceName: cutName.slice(0, -CUT_SUFFIX.length),
    inventoryCount: inventoryNames.length,
    resultCount: resultSet.size,
    missingResults,
    foreignResults,
    duplicateResults,
    failureCount: snapshot.session.failures.length,
    hasPendingOperation: snapshot.session.pendingOperation !== null,
    accepted: snapshot.review.completedAt !== null,
    automaticCorrectionCount: automaticCorrections.length,
    effectiveCorrectionCount: effectiveCorrections.length,
    operatorOnlyCorrectionCount: effectiveCorrections.filter(
      (name) => !automaticCorrections.includes(name),
    ).length,
  };
  if (base.accepted) return { ...base, eligibility: 'accepted' };
  if (
    missingResults > 0 ||
    foreignResults > 0 ||
    duplicateResults > 0 ||
    base.failureCount > 0 ||
    base.hasPendingOperation
  )
    return { ...base, eligibility: 'incomplete' };
  if (automaticCorrections.length === 0)
    return {
      ...base,
      eligibility:
        effectiveCorrections.length > 0 ? 'operator_only' : 'no_corrections',
    };
  if (!sourceAvailable) return { ...base, eligibility: 'source_missing' };
  return { ...base, eligibility: 'eligible' };
}

export async function auditSelectedCropCorrectionDirectories(rootArgument) {
  const rootDirectory = path.resolve(rootArgument);
  await safeDirectory(rootDirectory);
  const entries = (await fs.readdir(rootDirectory, { withFileTypes: true }))
    .filter(
      (entry) =>
        entry.isDirectory() &&
        !entry.isSymbolicLink() &&
        entry.name.endsWith(CUT_SUFFIX),
    )
    .sort((left, right) => natural.compare(left.name, right.name));
  const directories = [];
  for (const entry of entries) {
    const cutDirectory = path.join(rootDirectory, entry.name);
    const sourceName = entry.name.slice(0, -CUT_SUFFIX.length);
    const sourceDirectory = path.join(rootDirectory, sourceName);
    const stateDirectory = path.join(cutDirectory, '.manual-image-crop-state');
    if (!(await exists(stateDirectory))) {
      directories.push({
        cutName: entry.name,
        sourceName,
        eligibility: 'state_missing',
      });
      continue;
    }
    try {
      const sourceAvailable = await exists(sourceDirectory);
      if (sourceAvailable) await safeDirectory(sourceDirectory);
      const snapshot = await readSnapshot(cutDirectory);
      if (
        snapshot.inventory.outputDirectoryName !== entry.name ||
        snapshot.inventory.sourceDirectoryName !== sourceName
      )
        throw new Error('CROP_BATCH_IDENTITY_MISMATCH');
      directories.push(classifySnapshot(snapshot, entry.name, sourceAvailable));
    } catch (cause) {
      directories.push({
        cutName: entry.name,
        sourceName,
        eligibility: 'invalid_state',
        error: cause instanceof Error ? cause.message : 'UNKNOWN_ERROR',
      });
    }
  }
  return { rootDirectory, fingerprint: CROP_V12_FINGERPRINT, directories };
}

async function atomicJson(file, value) {
  const part = `${file}.part`;
  if (await exists(part)) {
    const info = await fs.lstat(part);
    if (!info.isFile() || info.isSymbolicLink())
      throw new Error('CROP_BATCH_REPORT_PATH_UNSAFE');
    await fs.unlink(part);
  }
  if (await exists(file)) {
    const previous = await readJson(file);
    if (
      previous?.schemaVersion !== 1 ||
      previous?.rootDirectory !== value.rootDirectory
    )
      throw new Error('CROP_BATCH_REPORT_FOREIGN');
  }
  const handle = await fs.open(part, 'wx');
  try {
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`);
    await handle.sync();
  } finally {
    await handle.close();
  }
  await fs.rename(part, file);
}

export async function runSelectedCropCorrectionDirectoryBatch(
  rootArgument,
  {
    runPreview = runSelectedCropCorrectionPreview,
    onProgress = () => {},
    writeReport = true,
  } = {},
) {
  const audit = await auditSelectedCropCorrectionDirectories(rootArgument);
  const startedAt = new Date().toISOString();
  const directories = audit.directories.map((item) => ({ ...item }));
  const reportFile = path.join(audit.rootDirectory, BATCH_REPORT_NAME);
  const report = () => ({
    schemaVersion: 1,
    rootDirectory: audit.rootDirectory,
    fingerprint: audit.fingerprint,
    startedAt,
    completedAt: null,
    directories,
  });
  if (writeReport) await atomicJson(reportFile, report());
  for (const directory of directories) {
    if (directory.eligibility !== 'eligible') continue;
    const sourceDirectory = path.join(
      audit.rootDirectory,
      directory.sourceName,
    );
    const cutDirectory = path.join(audit.rootDirectory, directory.cutName);
    const previewDirectory = `${cutDirectory}${PREVIEW_SUFFIX}`;
    try {
      const preview = await runPreview(
        sourceDirectory,
        cutDirectory,
        previewDirectory,
        {
          onProgress: (progress) =>
            onProgress({ directory: directory.cutName, ...progress }),
        },
      );
      Object.assign(directory, {
        runStatus:
          preview.failures.length > 0 ? 'completed_with_failures' : 'completed',
        previewDirectory,
        previewTotal: preview.total,
        previewCompleted: preview.completed,
        previewAutomatic: preview.automatic,
        previewStructural: preview.structural,
        previewRegistered: preview.registered,
        previewBoardBuffered: preview.boardBuffered,
        previewManual: preview.manual,
        previewFailureCount: preview.failures.length,
      });
    } catch (cause) {
      Object.assign(directory, {
        runStatus: 'failed',
        previewDirectory,
        runError: cause instanceof Error ? cause.message : 'UNKNOWN_ERROR',
      });
    }
    if (writeReport) await atomicJson(reportFile, report());
  }
  const finalReport = { ...report(), completedAt: new Date().toISOString() };
  if (writeReport) await atomicJson(reportFile, finalReport);
  return finalReport;
}

async function main() {
  const [rootDirectory, mode] = process.argv.slice(2);
  if (!rootDirectory) throw new Error('Usage: <root-directory> [--audit-only]');
  if (mode === '--audit-only') {
    process.stdout.write(
      `${JSON.stringify(await auditSelectedCropCorrectionDirectories(rootDirectory), null, 2)}\n`,
    );
    return;
  }
  if (mode !== undefined) throw new Error('CROP_BATCH_MODE_INVALID');
  const lastReportedCompleted = new Map();
  const report = await runSelectedCropCorrectionDirectoryBatch(rootDirectory, {
    onProgress: (progress) => {
      if (lastReportedCompleted.get(progress.directory) === progress.completed)
        return;
      lastReportedCompleted.set(progress.directory, progress.completed);
      if (
        progress.completed % 25 === 0 ||
        progress.completed === progress.total
      )
        process.stdout.write(`${JSON.stringify(progress)}\n`);
    },
  });
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
  if (
    report.directories.some(
      (directory) =>
        directory.runStatus === 'failed' ||
        directory.runStatus === 'completed_with_failures',
    )
  )
    process.exitCode = 1;
}

if (
  process.argv[1] &&
  pathToFileURL(path.resolve(process.argv[1])).href === import.meta.url
)
  await main();
