import { createHash } from 'node:crypto';
import { readFile, readdir } from 'node:fs/promises';
import { basename, dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const SEQUENCE_FILE = /^seq_(\d+)-(\d+)\.jpe?g$/i;

export function previewManualSelectionManifestV2({
  manifest,
  outputChecksums,
  sequenceUpperBound,
}) {
  if (
    typeof manifest !== 'object' ||
    manifest === null ||
    (manifest.schemaVersion !== 1 && manifest.schemaVersion !== 2) ||
    !Array.isArray(manifest.items) ||
    !Number.isSafeInteger(sequenceUpperBound) ||
    sequenceUpperBound < 1
  ) {
    throw new Error('MANUAL_SELECTION_DIAGNOSTIC_INPUT_INVALID');
  }

  const filesByStart = new Map();
  for (const [name, checksum] of outputChecksums) {
    const match = SEQUENCE_FILE.exec(name);
    if (match === null) continue;
    const start = Number(match[1]);
    const end = Number(match[2]);
    if (start < 1 || end < start || end - start + 1 > 9) continue;
    const candidates = filesByStart.get(start) ?? [];
    candidates.push({ checksum, end, name, start });
    filesByStart.set(start, candidates);
  }

  const issues = [];
  const items = [];
  for (const [index, item] of manifest.items.entries()) {
    if (
      typeof item !== 'object' ||
      item === null ||
      !Number.isSafeInteger(item.rangeStart) ||
      !Number.isSafeInteger(item.rangeEnd) ||
      typeof item.outputName !== 'string' ||
      typeof item.imageChecksum !== 'string'
    ) {
      issues.push({ code: 'MANIFEST_ITEM_INVALID', index });
      continue;
    }
    const candidates = (filesByStart.get(item.rangeStart) ?? []).filter(
      (candidate) => candidate.end <= sequenceUpperBound,
    );
    const exact = candidates.find(
      (candidate) =>
        candidate.name.toLowerCase() === item.outputName.toLowerCase(),
    );
    const candidate = exact ?? (candidates.length === 1 ? candidates[0] : null);
    if (candidate === null) {
      issues.push({
        code: candidates.length > 1 ? 'OUTPUT_AMBIGUOUS' : 'OUTPUT_MISSING',
        index,
        outputName: item.outputName,
      });
      continue;
    }
    if (candidate.checksum !== item.imageChecksum) {
      issues.push({
        code: 'OUTPUT_CHECKSUM_MISMATCH',
        index,
        outputName: candidate.name,
      });
      continue;
    }
    items.push({
      ...item,
      activeBoardCount: candidate.end - candidate.start + 1,
      outputName: candidate.name,
      rangeEnd: candidate.end,
      rangeStart: candidate.start,
    });
  }

  const selectionComplete =
    items.length > 0 &&
    items.some((item) => item.rangeEnd === sequenceUpperBound);
  return {
    canMaterializeV2:
      issues.length === 0 && items.length === manifest.items.length,
    issues,
    proposedManifest:
      issues.length === 0 && items.length === manifest.items.length
        ? {
            ...manifest,
            schemaVersion: 2,
            items,
            selectionComplete,
            sequenceUpperBound,
          }
        : null,
    writesPerformed: 0,
  };
}

async function sha256(path) {
  return createHash('sha256')
    .update(await readFile(path))
    .digest('hex');
}

async function main() {
  const manifestPath = process.argv[2];
  const sequenceUpperBound = Number(process.argv[3]);
  if (manifestPath === undefined || !Number.isSafeInteger(sequenceUpperBound)) {
    throw new Error(
      'Usage: node scripts/preview_manual_selection_manifest_v2.mjs <manifest-path> <sequence-upper-bound>',
    );
  }
  const absoluteManifestPath = resolve(manifestPath);
  const outputDirectory = dirname(absoluteManifestPath);
  const names = await readdir(outputDirectory);
  const sequenceNames = names.filter((name) => SEQUENCE_FILE.test(name));
  const outputChecksums = new Map(
    await Promise.all(
      sequenceNames.map(async (name) => [
        name,
        await sha256(resolve(outputDirectory, name)),
      ]),
    ),
  );
  const manifest = JSON.parse(await readFile(absoluteManifestPath, 'utf8'));
  process.stdout.write(
    `${JSON.stringify(
      {
        manifest: basename(absoluteManifestPath),
        ...previewManualSelectionManifestV2({
          manifest,
          outputChecksums,
          sequenceUpperBound,
        }),
      },
      null,
      2,
    )}\n`,
  );
}

if (
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  await main();
}
