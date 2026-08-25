const naturalPathCollator = new Intl.Collator('en', {
  numeric: true,
  sensitivity: 'base',
});

export const REMOTE_SOURCE_MANIFEST_SCHEMA = 'remote-source-manifest-v1';
export const REMOTE_SOURCE_CAPABILITY_REPORT_SCHEMA =
  'remote-source-capability-report-v1';
export const CAPABILITY_DATABASE_NAME =
  'game-predictor-remote-source-capability-spike';
const CAPABILITY_DATABASE_VERSION = 1;
const CAPABILITY_HANDLE_STORE = 'handles';

export function normalizeRelativeSourcePath(value) {
  if (typeof value !== 'string') {
    throw new TypeError('A source path must be a string.');
  }
  const normalized = value.normalize('NFC');
  if (
    normalized.length === 0 ||
    normalized.includes('\0') ||
    normalized.includes('\\') ||
    normalized.startsWith('/') ||
    normalized.endsWith('/') ||
    /^[a-zA-Z]:/.test(normalized)
  ) {
    throw new Error('An absolute or malformed source path is not allowed.');
  }
  const segments = normalized.split('/');
  if (
    segments.some(
      (segment) => segment.length === 0 || segment === '.' || segment === '..',
    )
  ) {
    throw new Error('A source path contains a forbidden segment.');
  }
  return segments.join('/');
}

export function naturalSourcePathCompare(left, right) {
  return naturalPathCollator.compare(left, right);
}

export function sourceMetadataFromFile(file, relativePath) {
  const sourcePath = normalizeRelativeSourcePath(
    relativePath || file.webkitRelativePath || file.relativePath || file.name,
  );
  const name = sourcePath.split('/').at(-1);
  if (!name || !/\.jpe?g$/i.test(name)) {
    throw new Error(`Only JPEG source metadata is accepted: ${sourcePath}`);
  }
  const sizeBytes = Number(file.size);
  const lastModifiedMs = Number(file.lastModified);
  if (!Number.isSafeInteger(sizeBytes) || sizeBytes < 0) {
    throw new Error(`Invalid source size: ${sourcePath}`);
  }
  if (!Number.isSafeInteger(lastModifiedMs) || lastModifiedMs < 0) {
    throw new Error(`Invalid source modification time: ${sourcePath}`);
  }
  return Object.freeze({
    relativePath: sourcePath,
    name,
    sizeBytes,
    lastModifiedMs,
    mimeType: typeof file.type === 'string' ? file.type : '',
  });
}

export async function buildRemoteSourceManifest(
  files,
  { sourceKind = 'directory_handle' } = {},
) {
  const entries = Array.from(files, (file) => sourceMetadataFromFile(file));
  entries.sort((left, right) =>
    naturalSourcePathCompare(left.relativePath, right.relativePath),
  );
  const duplicate = entries.find(
    (entry, index) =>
      index > 0 && entry.relativePath === entries[index - 1].relativePath,
  );
  if (duplicate) {
    throw new Error(`Duplicate source path: ${duplicate.relativePath}`);
  }
  const canonicalEntries = entries.map((entry, index) => ({
    ordinal: index,
    ...entry,
  }));
  const manifestWithoutChecksum = {
    schemaVersion: REMOTE_SOURCE_MANIFEST_SCHEMA,
    sourceKind,
    fileCount: canonicalEntries.length,
    totalBytes: canonicalEntries.reduce(
      (total, entry) => total + entry.sizeBytes,
      0,
    ),
    entries: canonicalEntries,
  };
  return Object.freeze({
    ...manifestWithoutChecksum,
    manifestChecksumSha256: await sha256Canonical(manifestWithoutChecksum),
  });
}

export async function listDirectoryHandleMetadata(directoryHandle) {
  const files = [];
  await appendDirectoryMetadata(directoryHandle, '', files);
  return files;
}

async function appendDirectoryMetadata(directoryHandle, prefix, output) {
  for await (const [name, handle] of directoryHandle.entries()) {
    const relativePath = prefix ? `${prefix}/${name}` : name;
    if (handle.kind === 'directory') {
      await appendDirectoryMetadata(handle, relativePath, output);
      continue;
    }
    if (handle.kind !== 'file' || !/\.jpe?g$/i.test(name)) {
      continue;
    }
    const file = await handle.getFile();
    output.push({
      name: file.name,
      relativePath,
      size: file.size,
      lastModified: file.lastModified,
      type: file.type,
    });
  }
}

export function detectRemoteSourceCapabilities(scope = globalThis) {
  const inputPrototype = scope.HTMLInputElement?.prototype;
  const capabilities = {
    secureContext: scope.isSecureContext === true,
    showDirectoryPicker:
      typeof scope.showDirectoryPicker === 'function' &&
      scope.isSecureContext === true,
    indexedDb: typeof scope.indexedDB?.open === 'function',
    originPrivateFileSystem:
      typeof scope.navigator?.storage?.getDirectory === 'function',
    webkitDirectoryFallback:
      inputPrototype != null && 'webkitdirectory' in inputPrototype,
  };
  return Object.freeze({
    ...capabilities,
    recommendedMode:
      capabilities.showDirectoryPicker && capabilities.indexedDb
        ? 'directory_handle'
        : capabilities.webkitDirectoryFallback
          ? 'webkitdirectory_reselect'
          : 'unsupported',
  });
}

export async function queryReadPermission(directoryHandle) {
  if (typeof directoryHandle?.queryPermission !== 'function') {
    return 'unsupported';
  }
  try {
    return await directoryHandle.queryPermission({ mode: 'read' });
  } catch {
    return 'error';
  }
}

export async function requestReadPermission(directoryHandle) {
  if (typeof directoryHandle?.requestPermission !== 'function') {
    return 'unsupported';
  }
  try {
    return await directoryHandle.requestPermission({ mode: 'read' });
  } catch {
    return 'error';
  }
}

export async function saveCapabilityHandle(indexedDb, key, handle) {
  const database = await openCapabilityDatabase(indexedDb);
  try {
    await requestToPromise(
      database
        .transaction(CAPABILITY_HANDLE_STORE, 'readwrite')
        .objectStore(CAPABILITY_HANDLE_STORE)
        .put(handle, key),
    );
  } finally {
    database.close();
  }
}

export async function loadCapabilityHandle(indexedDb, key) {
  const database = await openCapabilityDatabase(indexedDb);
  try {
    return await requestToPromise(
      database
        .transaction(CAPABILITY_HANDLE_STORE, 'readonly')
        .objectStore(CAPABILITY_HANDLE_STORE)
        .get(key),
    );
  } finally {
    database.close();
  }
}

export async function clearCapabilityDatabase(indexedDb) {
  await requestToPromise(indexedDb.deleteDatabase(CAPABILITY_DATABASE_NAME));
}

function openCapabilityDatabase(indexedDb) {
  if (typeof indexedDb?.open !== 'function') {
    throw new Error('IndexedDB is unavailable.');
  }
  const request = indexedDb.open(
    CAPABILITY_DATABASE_NAME,
    CAPABILITY_DATABASE_VERSION,
  );
  request.onupgradeneeded = () => {
    const database = request.result;
    if (!database.objectStoreNames.contains(CAPABILITY_HANDLE_STORE)) {
      database.createObjectStore(CAPABILITY_HANDLE_STORE);
    }
  };
  return requestToPromise(request);
}

function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () =>
      reject(request.error ?? new Error('IDB request failed.'));
  });
}

export function compareRelinkManifest(expected, candidate) {
  if (
    expected.schemaVersion !== REMOTE_SOURCE_MANIFEST_SCHEMA ||
    candidate.schemaVersion !== REMOTE_SOURCE_MANIFEST_SCHEMA
  ) {
    return Object.freeze({ status: 'incompatible', changedFileCount: null });
  }
  if (expected.manifestChecksumSha256 === candidate.manifestChecksumSha256) {
    return Object.freeze({ status: 'same', changedFileCount: 0 });
  }
  const expectedByPath = new Map(
    expected.entries.map((entry) => [entry.relativePath, entry]),
  );
  const candidateByPath = new Map(
    candidate.entries.map((entry) => [entry.relativePath, entry]),
  );
  const paths = new Set([...expectedByPath.keys(), ...candidateByPath.keys()]);
  let changedFileCount = 0;
  for (const path of paths) {
    const left = expectedByPath.get(path);
    const right = candidateByPath.get(path);
    if (
      left == null ||
      right == null ||
      left.sizeBytes !== right.sizeBytes ||
      left.lastModifiedMs !== right.lastModifiedMs ||
      left.mimeType !== right.mimeType
    ) {
      changedFileCount += 1;
    }
  }
  return Object.freeze({ status: 'different', changedFileCount });
}

export function createSyntheticJpegMetadata(count) {
  if (!Number.isSafeInteger(count) || count < 0) {
    throw new Error('Synthetic file count must be a non-negative integer.');
  }
  return Array.from({ length: count }, (_, index) => {
    const number = count - index;
    return Object.freeze({
      name: `image_${number}.jpg`,
      relativePath: `batch_${Math.floor((number - 1) / 250) + 1}/image_${number}.jpg`,
      size: 300_000 + (number % 97),
      lastModified: 1_700_000_000_000 + number,
      type: 'image/jpeg',
      arrayBuffer() {
        throw new Error('Synthetic benchmark must not read image bytes.');
      },
    });
  });
}

export async function benchmarkSyntheticManifests(
  counts,
  now = () => performance.now(),
) {
  const results = [];
  for (const count of counts) {
    const files = createSyntheticJpegMetadata(count);
    const startedAt = now();
    const manifest = await buildRemoteSourceManifest(files, {
      sourceKind: 'synthetic_metadata',
    });
    const durationMs = Math.max(0, now() - startedAt);
    results.push({
      fileCount: manifest.fileCount,
      totalBytes: manifest.totalBytes,
      durationMs: Number(durationMs.toFixed(3)),
      manifestChecksumSha256: manifest.manifestChecksumSha256,
      decodedFileCount: 0,
      byteReadCount: 0,
    });
  }
  return Object.freeze(results);
}

export async function attachCapabilityReportChecksum(reportWithoutChecksum) {
  return Object.freeze({
    ...reportWithoutChecksum,
    reportChecksumSha256: await sha256Canonical(reportWithoutChecksum),
  });
}

export async function verifyCapabilityReportChecksum(report) {
  if (report.schemaVersion !== REMOTE_SOURCE_CAPABILITY_REPORT_SCHEMA) {
    return false;
  }
  const { reportChecksumSha256, ...withoutChecksum } = report;
  return reportChecksumSha256 === (await sha256Canonical(withoutChecksum));
}

export async function sha256Canonical(value) {
  const encoded = new TextEncoder().encode(stableStringify(value));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', encoded);
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`;
  }
  if (value != null && typeof value === 'object') {
    const entries = Object.entries(value).sort(([left], [right]) =>
      left.localeCompare(right, 'en'),
    );
    return `{${entries
      .map(([key, child]) => `${JSON.stringify(key)}:${stableStringify(child)}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}
