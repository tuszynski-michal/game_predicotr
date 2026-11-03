import type { AdminApiClient } from '@game-predictor/admin-api-client';
import {
  assertCurrentReplacementEntry,
  commitReplacementWrite,
  createReplacementRepair,
  deriveReplacementFilledGaps,
  deriveReplacementStagingSelection,
  parseReplacementRequest,
  replacementCanonicalJson,
  replacementRequestPayload,
  validateReplacementRepair,
  validateReplacementTarget,
  type ReplacementRepairManifest,
  type ReplacementRequest,
  type ReplacementWrite,
} from '@game-predictor/manual-image-selection-core/replacement-repair';
import {
  parseSequenceFileName,
  validateFilledGapsManifest,
} from '@game-predictor/manual-image-selection-core/repair';
import { sha256Hex } from './manual-image-selection-fsa-adapter.ts';

export const REPLACEMENT_REPAIR_NAME = 'manual-image-selection-repair-v3.json';
const HANDOFF = 'manual-image-selection-filled-gaps-v1.json';
type CurrentApi = Pick<AdminApiClient, 'getSourceReplacementBatch'>;
export interface ReplacementSource {
  readonly fileName: string;
  readonly entryId: string;
  readonly handle: FileSystemFileHandle;
}
const missing = (cause: unknown) =>
  cause instanceof DOMException && cause.name === 'NotFoundError';

async function fileOrNull(
  directory: FileSystemDirectoryHandle,
  name: string,
): Promise<File | null> {
  try {
    return await (await directory.getFileHandle(name)).getFile();
  } catch (cause) {
    if (missing(cause)) return null;
    throw cause;
  }
}
async function jsonWrite(
  directory: FileSystemDirectoryHandle,
  name: string,
  value: unknown,
): Promise<void> {
  const stream = await (
    await directory.getFileHandle(name, { create: true })
  ).createWritable();
  try {
    await stream.write(`${JSON.stringify(value, null, 2)}\n`);
    await stream.close();
  } catch (cause) {
    await stream.abort().catch(() => undefined);
    throw cause;
  }
}

export async function readReplacementRequest(
  value: unknown,
): Promise<ReplacementRequest> {
  const request = parseReplacementRequest(value);
  const checksum = await sha256Hex(
    new Blob([replacementCanonicalJson(replacementRequestPayload(request))]),
  );
  if (checksum !== request.digest)
    throw new Error('REPLACEMENT_REQUEST_DIGEST_MISMATCH');
  return request;
}

export async function readReplacementRepair(
  directory: FileSystemDirectoryHandle,
): Promise<ReplacementRepairManifest | null> {
  const file = await fileOrNull(directory, REPLACEMENT_REPAIR_NAME);
  if (file === null) return null;
  const manifest = validateReplacementRepair(JSON.parse(await file.text()));
  await readReplacementRequest(manifest.request);
  if (manifest.selectedDirectoryName !== directory.name)
    throw new Error('REPLACEMENT_DIRECTORY_CHANGED');
  return manifest;
}

export async function assertSeparateReplacementDirectories(
  source: FileSystemDirectoryHandle,
  output: FileSystemDirectoryHandle,
): Promise<void> {
  if (
    (await source.isSameEntry(output)) ||
    (await source.resolve(output)) !== null ||
    (await output.resolve(source)) !== null
  )
    throw new Error('REPLACEMENT_OUTPUT_MUST_BE_SEPARATE');
}

/** Listing never reads image bytes and never writes to the source directory. */
export async function listReplacementSources(
  directory: FileSystemDirectoryHandle,
  request: ReplacementRequest,
): Promise<readonly ReplacementSource[]> {
  const sources: ReplacementSource[] = [];
  for await (const [name, handle] of directory.entries()) {
    if (handle.kind !== 'file' || !/\.jpe?g$/i.test(name)) continue;
    // Unselected photos can share the read-only source folder. They never become targets.
    let parsed;
    try {
      parsed = parseSequenceFileName(name);
    } catch (cause) {
      if (
        cause instanceof Error &&
        /^(INVALID_SEQUENCE_FILE_NAME|INVALID_SEQUENCE_RANGE):/.test(
          cause.message,
        )
      )
        continue;
      throw cause;
    }
    const range = request.allowedRanges.find(
      (item) =>
        item.sequenceStart === parsed.start && item.sequenceEnd === parsed.end,
    );
    if (!range) continue;
    sources.push({ fileName: name, entryId: range.entryId, handle });
  }
  return sources.sort((a, b) => a.fileName.localeCompare(b.fileName));
}

async function assertOutputInventory(
  directory: FileSystemDirectoryHandle,
  manifest: ReplacementRepairManifest | null,
): Promise<void> {
  const expected = new Set(
    manifest?.journal.map((write) => write.fileName) ?? [],
  );
  if (manifest) {
    expected.add(REPLACEMENT_REPAIR_NAME);
    expected.add(HANDOFF);
  }
  for await (const [name] of directory.entries()) {
    if (!expected.has(name)) {
      if (name.endsWith('.crswap') && expected.has(name.slice(0, -7)))
        throw new Error(`REPLACEMENT_TEMPORARY_WRITE_REMAINS:${name}`);
      throw new Error(`REPLACEMENT_FOREIGN_FILE:${name}`);
    }
  }
  if (manifest) {
    const file = await fileOrNull(directory, HANDOFF);
    if (file) {
      const text = await file.text();
      let handoff;
      try {
        handoff = validateFilledGapsManifest(JSON.parse(text));
      } catch (cause) {
        throw new Error('REPLACEMENT_FOREIGN_HANDOFF', { cause });
      }
      if (
        handoff.repairKey !== manifest.repairKey ||
        handoff.selectedDirectoryName !== manifest.selectedDirectoryName ||
        handoff.repairRevision > manifest.revision ||
        new Set(handoff.entries.map((entry) => entry.fillOperationId)).size !==
          handoff.entries.length
      )
        throw new Error('REPLACEMENT_FOREIGN_HANDOFF');
      for (const entry of handoff.entries) {
        const write = manifest.journal.find(
          (row) =>
            row.state === 'committed' && row.id === entry.fillOperationId,
        );
        if (
          !write ||
          entry.fileName !== write.fileName ||
          entry.checksumSha256 !== write.checksumSha256 ||
          entry.sourcePath !== write.sourcePath ||
          entry.sourceIndex !== write.sourceIndex ||
          entry.filledAt !== write.occurredAt ||
          entry.start !== parseSequenceFileName(write.fileName).start ||
          entry.end !== parseSequenceFileName(write.fileName).end
        )
          throw new Error('REPLACEMENT_FOREIGN_HANDOFF');
      }
    }
  }
}

/** Verify every managed output exactly once, then derive the unchanged legacy handoff. */
export async function inspectReplacementOutput(
  directory: FileSystemDirectoryHandle,
  request?: ReplacementRequest,
): Promise<ReplacementRepairManifest | null> {
  return serialize(directory.name.toLocaleLowerCase('en-US'), () =>
    inspectOutputUnlocked(directory, request),
  );
}

async function inspectOutputUnlocked(
  directory: FileSystemDirectoryHandle,
  request?: ReplacementRequest,
): Promise<ReplacementRepairManifest | null> {
  let manifest = await readReplacementRepair(directory);
  if (
    request &&
    manifest &&
    replacementCanonicalJson(request) !==
      replacementCanonicalJson(manifest.request)
  )
    throw new Error('REPLACEMENT_FOREIGN_MANIFEST');
  await assertOutputInventory(directory, manifest);
  if (!manifest) return null;
  const verified: Array<{
    fileName: string;
    checksumSha256: string;
    size: number;
  }> = [];
  for (const write of manifest.journal) {
    const file = await verifyReplacementFile(directory, write);
    if (!file) continue; // An intent without a JPEG requires the original chosen source.
    verified.push({
      fileName: write.fileName,
      checksumSha256: write.checksumSha256,
      size: file.size,
    });
    if (write.state === 'intent') {
      await verifyJpeg(file);
      manifest = commitReplacementWrite(
        manifest,
        write.id,
        new Date().toISOString(),
      );
    }
  }
  // A crash between these writes is repaired by the next inspection.
  await jsonWrite(directory, REPLACEMENT_REPAIR_NAME, manifest);
  await jsonWrite(
    directory,
    HANDOFF,
    deriveReplacementFilledGaps(manifest, verified),
  );
  return manifest;
}

export async function readReplacementFilledGaps(
  directory: FileSystemDirectoryHandle,
) {
  return serialize(directory.name.toLocaleLowerCase('en-US'), async () => {
    const manifest = await readReplacementRepair(directory);
    await assertOutputInventory(directory, manifest);
    if (!manifest) return null;
    const verified = [];
    for (const write of manifest.journal) {
      if (write.state !== 'committed') continue;
      const file = await verifyReplacementFile(directory, write);
      verified.push({
        fileName: write.fileName,
        checksumSha256: write.checksumSha256,
        size: file!.size,
      });
    }
    // Crop sources have read permission only: no recovery commit or filesystem writes here.
    return deriveReplacementFilledGaps(manifest, verified);
  });
}

/** Read-only handoff: only persisted committed writes with verified bytes. */
export async function readReplacementImportSelection(
  directory: FileSystemDirectoryHandle,
  selectedEntryIds: readonly string[],
) {
  return serialize(directory.name.toLocaleLowerCase('en-US'), async () => {
    const manifest = await readReplacementRepair(directory);
    await assertOutputInventory(directory, manifest);
    if (!manifest)
      throw new Error('Brak zapisanego planu przygotowanych zamienników.');
    const verified = [];
    const files = new Map<string, File>();
    for (const write of manifest.journal) {
      if (write.state !== 'committed') continue;
      const file = await verifyReplacementFile(directory, write);
      verified.push({
        fileName: write.fileName,
        checksumSha256: write.checksumSha256,
        size: file!.size,
      });
      files.set(write.fileName, file!);
    }
    const selection = deriveReplacementStagingSelection(
      manifest,
      verified,
      selectedEntryIds,
    );
    return {
      selection,
      files: selection.files.map((item) => files.get(item.fileName)!),
    };
  });
}

async function verifyReplacementFile(
  directory: FileSystemDirectoryHandle,
  write: ReplacementWrite,
): Promise<File | null> {
  const file = await fileOrNull(directory, write.fileName);
  if (!file) {
    if (write.state === 'committed')
      throw new Error('REPLACEMENT_COMMITTED_FILE_MISSING');
    return null;
  }
  if (
    file.size !== write.size ||
    (await sha256Hex(file)) !== write.checksumSha256
  )
    throw new Error(`REPLACEMENT_FILE_CHANGED:${write.fileName}`);
  return file;
}

async function verifyJpeg(file: File): Promise<void> {
  const first = new Uint8Array(await file.slice(0, 2).arrayBuffer());
  const last = new Uint8Array(await file.slice(-2).arrayBuffer());
  if (
    first[0] !== 0xff ||
    first[1] !== 0xd8 ||
    last[0] !== 0xff ||
    last[1] !== 0xd9
  )
    throw new Error('REPLACEMENT_INVALID_JPEG');
  if (typeof globalThis.createImageBitmap === 'function') {
    const image = await createImageBitmap(file);
    image.close();
  }
}

/** A new write always rechecks only its own entry against the configured authenticated API. */
export async function authorizeReplacementWrite(
  api: CurrentApi,
  request: ReplacementRequest,
  entryId: string,
): Promise<void> {
  const result = await api.getSourceReplacementBatch(
    request.gameId,
    request.batchId,
  );
  if (
    result.error ||
    !result.data ||
    result.data.gameId !== request.gameId ||
    result.data.id !== request.batchId
  )
    throw new Error('REPLACEMENT_CURRENT_API_REQUIRED');
  assertCurrentReplacementEntry(
    request,
    entryId,
    result.data.entries.find((entry) => entry.id === entryId),
  );
}

// Web Locks coordinates same-origin tabs; the fallback serializes adapter calls in tests.
const queues = new Map<string, Promise<unknown>>();
async function serialize<T>(
  key: string,
  operation: () => Promise<T>,
): Promise<T> {
  if (globalThis.navigator?.locks)
    return navigator.locks.request(`replacement-repair:${key}`, operation);
  const previous = queues.get(key) ?? Promise.resolve();
  const next = previous.catch(() => undefined).then(operation);
  queues.set(key, next);
  try {
    return await next;
  } finally {
    if (queues.get(key) === next) queues.delete(key);
  }
}

export async function writeReplacementPhoto(input: {
  readonly sourceDirectory: FileSystemDirectoryHandle;
  readonly output: FileSystemDirectoryHandle;
  readonly request: ReplacementRequest;
  readonly source: ReplacementSource;
  readonly api: CurrentApi;
}): Promise<ReplacementRepairManifest> {
  // Directory name deliberately over-serializes equal names: even foreign requests
  // targeting the same directory must share the same origin-wide lock.
  return serialize(input.output.name.toLocaleLowerCase('en-US'), async () => {
    const request = await readReplacementRequest(input.request);
    validateReplacementTarget(
      request,
      input.source.entryId,
      input.source.fileName,
    );
    await assertSeparateReplacementDirectories(
      input.sourceDirectory,
      input.output,
    );
    let manifest = await inspectOutputUnlocked(input.output, request);
    const existing = manifest?.journal.find(
      (write) => write.entryId === input.source.entryId,
    );
    if (existing?.state === 'committed') {
      const retriedSource = await input.source.handle.getFile();
      if (
        existing.sourcePath !== input.source.fileName ||
        existing.size !== retriedSource.size ||
        existing.checksumSha256 !== (await sha256Hex(retriedSource))
      )
        throw new Error('REPLACEMENT_ENTRY_ALREADY_PREPARED');
      return manifest!; // Lost response: immutable local receipt, no new write.
    }
    await authorizeReplacementWrite(input.api, request, input.source.entryId);
    const source = await input.source.handle.getFile();
    if (source.size === 0) throw new Error('REPLACEMENT_EMPTY_JPEG');
    await verifyJpeg(source);
    const checksumSha256 = await sha256Hex(source);
    if (request.entries.some((entry) => entry.sourceSha256 === checksumSha256))
      throw new Error('REPLACEMENT_RETIRED_SHA');
    const fileName = `seq_${parseSequenceFileName(input.source.fileName).start}-${parseSequenceFileName(input.source.fileName).end}.jpg`;
    const pending = manifest?.journal.find((write) => write.state === 'intent');
    if (
      pending &&
      (pending.entryId !== input.source.entryId ||
        pending.sourcePath !== input.source.fileName ||
        pending.checksumSha256 !== checksumSha256 ||
        pending.size !== source.size)
    )
      throw new Error('REPLACEMENT_PENDING_SOURCE_REQUIRED');
    const write: ReplacementWrite = pending ?? {
      id: crypto.randomUUID(),
      entryId: input.source.entryId,
      fileName,
      checksumSha256,
      size: source.size,
      sourcePath: input.source.fileName,
      sourceIndex: null,
      occurredAt: new Date().toISOString(),
      state: 'intent',
    };
    manifest ??= createReplacementRepair(
      request,
      crypto.randomUUID(),
      input.output.name,
      new Date().toISOString(),
    );
    if (!pending) {
      manifest = {
        ...manifest,
        revision: manifest.revision + 1,
        journal: [...manifest.journal, write],
      };
      validateReplacementRepair(manifest);
      await jsonWrite(input.output, REPLACEMENT_REPAIR_NAME, manifest);
    }
    // Recheck the target immediately before create; never adopt or overwrite an existing file.
    if (await fileOrNull(input.output, fileName))
      throw new Error('REPLACEMENT_TARGET_EXISTS');
    const stream = await (
      await input.output.getFileHandle(fileName, { create: true })
    ).createWritable();
    try {
      await stream.write(source);
      await stream.close();
    } catch (cause) {
      await stream.abort().catch(() => undefined);
      throw cause;
    }
    const written = await fileOrNull(input.output, fileName);
    if (
      !written ||
      written.size !== write.size ||
      (await sha256Hex(written)) !== checksumSha256
    )
      throw new Error('REPLACEMENT_WRITTEN_CHECKSUM_MISMATCH');
    manifest = commitReplacementWrite(
      manifest,
      write.id,
      new Date().toISOString(),
    );
    await jsonWrite(input.output, REPLACEMENT_REPAIR_NAME, manifest);
    // Also verifies older committed files before materializing any handoff.
    return (await inspectOutputUnlocked(input.output, request))!;
  });
}
