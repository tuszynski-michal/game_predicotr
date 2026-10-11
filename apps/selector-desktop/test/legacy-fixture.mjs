import {
  mkdir,
  mkdtemp,
  rm,
  writeFile,
  readFile,
  readdir,
  stat,
  utimes,
} from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { buildRemoteSourceManifestV1 } from '@game-predictor/manual-image-selection-core';
import { OUTPUT_MANIFEST_NAME } from '../src/manifest/operator-local.ts';
export const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
export const processes = {
  host: 'fixture-host',
  pid: process.pid,
  identity: async (pid) => (pid === process.pid ? 'fixture-process' : null),
};
export async function legacyFixture(
  t,
  {
    schemaVersion = 2,
    direction = 'ascending',
    traversal = 'natural_v2',
    terminal = false,
  } = {},
) {
  const base = path.resolve('.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(path.join(base, 'legacy-adoption-'));
  const stores = [];
  t.after(async () => {
    for (const store of stores) await store.close();
    if (!root.startsWith(base + path.sep))
      throw new Error('unsafe fixture cleanup');
    await rm(root, { recursive: true, force: true });
  });
  const sourceRoot = path.join(root, 'source'),
    oldOutputRoot = path.join(root, 'old-output');
  await mkdir(sourceRoot);
  await mkdir(oldOutputRoot);
  const names = ['photo1.jpg', 'photo2.jpeg', 'photo10.jpg', 'photo20.jpg'];
  const inventory = [];
  for (const name of names) {
    const bytes = Buffer.from([255, 216, ...Buffer.from(name), 255, 217]);
    const location = path.join(sourceRoot, name);
    await writeFile(location, bytes);
    await utimes(location, 1700000000, 1700000000.123);
    const metadata = await stat(location);
    inventory.push({
      relativePath: name,
      name,
      sizeBytes: metadata.size,
      lastModifiedMs: Math.trunc(metadata.mtimeMs),
      mimeType: 'image/jpeg',
    });
  }
  const fingerprint = await buildRemoteSourceManifestV1(
    inventory,
    'directory_handle',
  );
  const start = direction === 'ascending' ? 1 : 28;
  const accepted = {
    action: 'accepted',
    operationId: 'legacy-accepted',
    fileId: 'browser-photo-id',
    sourceIndex: 0,
    imagePath: names[0],
    imageChecksumSha256: hash(await readFile(path.join(sourceRoot, names[0]))),
    outputName: `seq_${start}-${start + 8}.jpg`,
    rangeStart: start,
    rangeEnd: start + 8,
    selectionGeneration: 7,
  };
  const skipStart = terminal
    ? direction === 'ascending'
      ? 37
      : 1
    : direction === 'ascending'
      ? 19
      : 10;
  const skipped = {
    action: 'skipped',
    operationId: 'legacy-skipped',
    fileId: null,
    sourceIndex: 3,
    imagePath: null,
    imageChecksumSha256: null,
    outputName: null,
    rangeStart: skipStart,
    rangeEnd: terminal && direction === 'ascending' ? 40 : skipStart + 8,
    selectionGeneration: 7,
  };
  const decisions = [accepted, skipped].map((d) =>
    schemaVersion === 2
      ? { ...d, activeBoardCount: d.rangeEnd - d.rangeStart + 1 }
      : d,
  );
  const manifest = {
    schemaVersion,
    storageMode: 'operator_local',
    sessionId: 'reviewer-session',
    batchId: 'reviewer-batch',
    sourceDirectoryName: 'source',
    sourceManifestChecksumSha256: fingerprint.manifestChecksumSha256,
    fileCount: names.length,
    firstLayout: start,
    direction,
    ...(traversal ? { sourceTraversalSemantics: traversal } : {}),
    ...(schemaVersion === 2
      ? {
          sequenceUpperBound: terminal && direction === 'ascending' ? 40 : null,
          selectionComplete: terminal,
        }
      : {}),
    decisions,
    currentIndex: 3,
    nextRangeStart: direction === 'ascending' ? (terminal ? 46 : 28) : 1,
    updatedAt: '2026-10-11T00:00:00.000Z',
  };
  const manifestPath = path.join(oldOutputRoot, OUTPUT_MANIFEST_NAME);
  async function save() {
    await writeFile(manifestPath, JSON.stringify(manifest));
  }
  await save();
  await writeFile(
    path.join(oldOutputRoot, accepted.outputName),
    await readFile(path.join(sourceRoot, names[0])),
  );
  const input = {
    sourceRoot,
    projectRoot: path.join(root, 'new-project'),
    outputRoot: path.join(root, 'new-output'),
    firstLayout: start,
    direction,
    sequenceUpperBound: manifest.sequenceUpperBound ?? null,
    localStorageConfirmed: true,
  };
  return {
    root,
    sourceRoot,
    oldOutputRoot,
    manifest,
    manifestPath,
    input,
    save,
    track(store) {
      stores.push(store);
      return store;
    },
  };
}
export async function originalProof(f) {
  const entries = [];
  for (const root of [f.sourceRoot, f.oldOutputRoot]) {
    for (const name of (await readdir(root)).sort()) {
      const file = path.join(root, name),
        info = await stat(file);
      entries.push([file, hash(await readFile(file)), info.size, info.mtimeMs]);
    }
  }
  return entries;
}
