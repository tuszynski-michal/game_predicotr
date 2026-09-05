import { promises as fs } from 'node:fs';
import path from 'node:path';
import { createHash } from 'node:crypto';
import sharp from 'sharp';
import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_POLICY,
} from '../../packages/manual-image-selection-core/src/auto-crop.ts';
import {
  prepareStructuralCrop,
  assertCropPreparationPolicy,
  CROP_V11_FINGERPRINT,
} from '../../packages/manual-image-selection-core/src/crop-preparation.ts';
import { CROP_V11_POLICY } from '../../packages/manual-image-selection-core/src/auto-crop-v11.ts';
import { validateSelectedImageCropSources } from '../../packages/manual-image-selection-core/src/crop.ts';
export const sha256 = (bytes) =>
  createHash('sha256').update(bytes).digest('hex');
async function optionalJson(file) {
  try {
    return JSON.parse(await fs.readFile(file, 'utf8'));
  } catch (e) {
    if (e.code === 'ENOENT') return null;
    throw e;
  }
}
async function exists(file) {
  try {
    await fs.lstat(file);
    return true;
  } catch (e) {
    if (e.code === 'ENOENT') return false;
    throw e;
  }
}
async function safe(file, directory = false) {
  const info = await fs.lstat(file);
  if (
    info.isSymbolicLink() ||
    (directory ? !info.isDirectory() : !info.isFile())
  )
    throw new Error(`CROP_PATH_UNSAFE:${file}`);
  if (
    (await fs.realpath(file)).toLowerCase() !== path.resolve(file).toLowerCase()
  )
    throw new Error(`CROP_PATH_UNSAFE:${file}`);
  return info;
}
async function atomic(file, value) {
  const part = `${file}.part`;
  if (await exists(part)) {
    await safe(part);
    await fs.unlink(part);
  } // Only this runner's state temp file.
  if (await exists(file)) await safe(file);
  const handle = await fs.open(part, 'wx');
  try {
    await handle.writeFile(JSON.stringify(value));
    await handle.sync();
  } finally {
    await handle.close();
  }
  await fs.rename(part, file);
}
async function verifyResult(source, output, result) {
  await safe(source);
  await safe(output);
  if (sha256(await fs.readFile(source)) !== result.sourceChecksumSha256)
    throw new Error('CROP_SOURCE_CHANGED');
  if (sha256(await fs.readFile(output)) !== result.outputChecksumSha256)
    throw new Error('CROP_OUTPUT_CHANGED');
}
export async function renderCropSource(bytes, policy) {
  assertCropPreparationPolicy(policy);
  const decoded = await sharp(bytes)
    .rotate()
    .ensureAlpha()
    .raw()
    .toBuffer({ resolveWithObject: true });
  let proposal;
  if (policy === CROP_V11_POLICY)
    proposal = await prepareStructuralCrop({
      width: decoded.info.width,
      height: decoded.info.height,
      rgba: new Uint8ClampedArray(decoded.data),
    });
  else {
    const sample = await sharp(decoded.data, { raw: decoded.info })
      .resize({ width: Math.min(512, decoded.info.width) })
      .raw()
      .toBuffer({ resolveWithObject: true });
    proposal = detectSelectedImageCropBand(
      {
        width: sample.info.width,
        height: sample.info.height,
        rgba: new Uint8ClampedArray(sample.data),
      },
      { width: decoded.info.width, height: decoded.info.height },
    );
  }
  const crop = proposal.crop;
  const output = await sharp(decoded.data, { raw: decoded.info })
    .extract({
      left: 0,
      top: crop.topY,
      width: crop.width,
      height: crop.bottomY - crop.topY,
    })
    .jpeg({ quality: 98 })
    .toBuffer();
  return { proposal, output };
}

/** Exclusive ownership, per-file intent, output verification, shard, intent clear.
 * hook is a crash-test seam; never sourced from user manifests. */
export async function processCropDirectory(
  sourcePath,
  policy = SELECTED_IMAGE_AUTO_CROP_POLICY,
  {
    hook = async () => {},
    render = renderCropSource,
    onProgress = () => {},
  } = {},
) {
  assertCropPreparationPolicy(policy);
  const source = path.resolve(sourcePath),
    parent = path.dirname(source),
    output = `${source} cut`;
  await safe(parent, true);
  await safe(source, true);
  if (source.endsWith(' cut')) throw new Error('CROP_SOURCE_IS_OUTPUT');
  const entries = [];
  for (const dirent of await fs.readdir(source, { withFileTypes: true })) {
    if (!/\.jpe?g$/i.test(dirent.name)) continue;
    const stat = await safe(path.join(source, dirent.name));
    entries.push({
      fileName: dirent.name,
      sizeBytes: stat.size,
      lastModifiedMs: Math.trunc(stat.mtimeMs),
    });
  }
  const files = validateSelectedImageCropSources(entries);
  const inventoryHash = sha256(
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
  if (!(await exists(output))) await fs.mkdir(output);
  await safe(output, true);
  if (await exists(path.join(output, '.manual-image-crop-state')))
    throw new Error('CROP_OUTPUT_OWNED_BY_BROWSER');
  const state = path.join(output, '.crop-preparation-v11'),
    metaPath = path.join(state, 'meta.json');
  if (!(await exists(state))) {
    const legacy = await optionalJson(
      path.join(output, 'manual-image-crop-output-v1.json'),
    );
    if (
      legacy &&
      legacy.sourceInventoryChecksumSha256 === inventoryHash &&
      legacy.entries?.length === files.length &&
      legacy.entries.every(
        (entry, index) =>
          entry.fileName === files[index].fileName &&
          entry.result?.autoCropProposal?.policyVersion === policy,
      )
    ) {
      for (const entry of legacy.entries)
        await verifyResult(
          path.join(source, entry.fileName),
          path.join(output, entry.fileName),
          entry.result,
        );
      return { prepared: files.length, total: files.length, failures: [] };
    }
    if ((await fs.readdir(output)).length)
      throw new Error('CROP_OUTPUT_FOREIGN');
    await fs.mkdir(state);
  }
  await safe(state, true);
  const lockPath = path.join(state, 'lock.json');
  if (await exists(lockPath)) {
    await safe(lockPath);
    const lock = await optionalJson(lockPath);
    if (!Number.isInteger(lock?.pid) || lock.pid < 1)
      throw new Error('CROP_LOCK_INVALID');
    let alive = true;
    try {
      process.kill(lock.pid, 0);
    } catch (e) {
      if (e.code === 'ESRCH') alive = false;
      else throw e;
    }
    if (alive) throw new Error('CROP_RUN_ACTIVE');
    await fs.unlink(lockPath);
  }
  const lock = await fs.open(lockPath, 'wx');
  await lock.writeFile(JSON.stringify({ pid: process.pid }));
  await lock.close();
  try {
    const meta = {
      schemaVersion: 1,
      sourceDirectoryName: path.basename(source),
      outputDirectoryName: path.basename(output),
      inventoryHash,
      policy,
      fingerprint:
        policy === CROP_V11_POLICY
          ? CROP_V11_FINGERPRINT
          : SELECTED_IMAGE_AUTO_CROP_POLICY,
    };
    const existing = await optionalJson(metaPath);
    if (existing && JSON.stringify(existing) !== JSON.stringify(meta))
      throw new Error('CROP_POLICY_OR_INVENTORY_CHANGED');
    if (!existing) await atomic(metaPath, meta);
    const results = new Map(),
      failures = [],
      blocked = new Set();
    const journalFile = (index) => path.join(state, `pending-${index}.json`);
    const partFile = (index) => path.join(state, `output-${index}.part`);
    const shardFile = (index) =>
      path.join(state, `results-${Math.floor(index / 64)}.json`);
    for (let index = 0; index < files.length; index += 64) {
      const shard = await optionalJson(shardFile(index));
      if (shard)
        for (const [name, result] of Object.entries(shard))
          results.set(name, result);
    }
    async function saveShard(index) {
      await atomic(
        shardFile(index),
        Object.fromEntries(
          files
            .slice(
              Math.floor(index / 64) * 64,
              Math.floor(index / 64) * 64 + 64,
            )
            .filter((f) => results.has(f.fileName))
            .map((f) => [f.fileName, results.get(f.fileName)]),
        ),
      );
    }
    for (let index = 0; index < files.length; index++) {
      const journal = journalFile(index),
        pending = await optionalJson(journal);
      if (!pending) continue;
      try {
        if (pending.fileName !== files[index].fileName)
          throw new Error('CROP_JOURNAL_FOREIGN');
        const target = path.join(output, pending.fileName);
        if (await exists(target)) {
          await verifyResult(
            path.join(source, pending.fileName),
            target,
            pending.result,
          );
          results.set(pending.fileName, pending.result);
          await saveShard(index);
        }
        const part = partFile(index);
        if (await exists(part)) {
          await safe(part);
          await fs.unlink(part);
        }
        await fs.unlink(journal);
      } catch (e) {
        blocked.add(files[index].fileName);
        failures.push({ fileName: files[index].fileName, code: e.message });
      }
    }
    const allowed = new Set([
      ...files.map((f) => f.fileName),
      '.crop-preparation-v11',
      'manual-image-crop-output-v1.json',
    ]);
    if ((await fs.readdir(output)).some((name) => !allowed.has(name)))
      throw new Error('CROP_OUTPUT_FOREIGN');
    for (let index = 0; index < files.length; index++) {
      const file = files[index],
        input = path.join(source, file.fileName),
        target = path.join(output, file.fileName),
        journal = journalFile(index);
      if (blocked.has(file.fileName)) continue;
      try {
        if (results.has(file.fileName)) {
          await verifyResult(input, target, results.get(file.fileName));
          continue;
        }
        if (await exists(target)) throw new Error('CROP_OUTPUT_UNTRACKED');
        const start = Date.now(),
          checkTime = () => {
            if (Date.now() - start > 120000)
              throw new Error('CROP_FILE_TIMEOUT');
          };
        await safe(input);
        const bytes = await fs.readFile(input),
          sourceHash = sha256(bytes);
        const { proposal, output: bytesOut } = await render(bytes, policy);
        checkTime();
        if (proposal.policyVersion !== policy)
          throw new Error('CROP_POLICY_MISMATCH');
        const result = {
          status: 'accepted',
          crop: proposal.crop,
          sourceChecksumSha256: sourceHash,
          outputChecksumSha256: sha256(bytesOut),
          acceptedAt: new Date().toISOString(),
          autoCropProposal: proposal,
        };
        const free = await fs.statfs(output);
        if (free.bavail * free.bsize < 30 * 1024 ** 3 + bytesOut.length * 1.2)
          throw new Error('STORAGE_CAPACITY_INSUFFICIENT');
        await atomic(journal, { fileName: file.fileName, result });
        await hook('intent', file.fileName);
        const part = partFile(index),
          handle = await fs.open(part, 'wx');
        try {
          await handle.writeFile(bytesOut);
          await handle.sync();
        } finally {
          await handle.close();
        }
        await hook('part', file.fileName);
        await safe(input);
        if (sha256(await fs.readFile(input)) !== sourceHash)
          throw new Error('CROP_SOURCE_CHANGED');
        checkTime();
        // link is no-clobber: a concurrent foreign target is never overwritten.
        await fs.link(part, target);
        await fs.unlink(part);
        await hook('publish', file.fileName);
        await verifyResult(input, target, result);
        results.set(file.fileName, result);
        await saveShard(index);
        await hook('shard', file.fileName);
        await fs.unlink(journal);
      } catch (e) {
        if (e.message === 'TEST_CRASH') throw e; // Test seam simulates process loss.
        // Leave this file's intent for retry; independent files can continue.
        failures.push({ fileName: file.fileName, code: e.message });
      }
      onProgress({
        completed: results.size,
        total: files.length,
        fileName: file.fileName,
      });
    }
    await atomic(path.join(state, 'failures.json'), failures);
    await atomic(path.join(output, 'manual-image-crop-output-v1.json'), {
      schemaVersion: 1,
      rendererVersion: 'manual-selected-image-band-crop-jpeg-v1',
      sourceDirectoryName: path.basename(source),
      outputDirectoryName: path.basename(output),
      sourceInventoryChecksumSha256: inventoryHash,
      revision: results.size,
      currentIndex: Math.max(0, files.length - 1),
      entries: files.map((f) => ({
        ...f,
        result: results.get(f.fileName) ?? null,
      })),
      reviewedFileNames: [],
      pendingOperation: null,
      updatedAt: new Date().toISOString(),
    });
    return { prepared: results.size, total: files.length, failures };
  } finally {
    await fs.unlink(lockPath);
  }
}
