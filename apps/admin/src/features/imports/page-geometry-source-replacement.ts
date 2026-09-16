import { pickLocalDirectory } from '../../lib/local-directory-picker.ts';

export interface PendingPageGeometryReplacement {
  replacementUploadId: string;
  replacementChecksum: string;
  sourceChecksum: string;
  sourceRelativePath: string;
}

export function pendingReplacementMatchesSource(
  source: { sourceChecksumSha256: string; sourceRelativePath: string } | null,
  candidate: unknown,
): candidate is PendingPageGeometryReplacement {
  if (source === null || candidate === null || typeof candidate !== 'object') return false;
  const pending = candidate as Partial<PendingPageGeometryReplacement>;
  return (
    pending.sourceChecksum === source.sourceChecksumSha256 &&
    pending.sourceRelativePath === source.sourceRelativePath &&
    typeof pending.replacementUploadId === 'string' &&
    typeof pending.replacementChecksum === 'string' &&
    /^[0-9a-f]{64}$/.test(pending.replacementChecksum)
  );
}

export async function choosePageGeometryCutFolder(): Promise<FileSystemDirectoryHandle> {
  return pickLocalDirectory({ id: 'gp-page-geometry-cut', mode: 'readwrite' });
}

async function sourceFileHandle(
  folder: FileSystemDirectoryHandle,
  sourceRelativePath: string,
): Promise<FileSystemFileHandle> {
  const parts = sourceRelativePath.replaceAll('\\', '/').split('/');
  if (
    parts.length < 2 ||
    parts[0] !== folder.name ||
    parts.some((part) => !part || part === '.' || part === '..')
  ) {
    throw new Error(
      `Wybierz katalog ${parts[0] ?? 'cut'} zawierający oryginalne zdjęcie.`,
    );
  }
  let current = folder;
  for (const part of parts.slice(1, -1)) {
    current = await current.getDirectoryHandle(part);
  }
  return current.getFileHandle(parts.at(-1)!);
}

async function sha256(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export const checksumPageGeometryFile = sha256;

export async function verifyPageGeometryCutSource(
  folder: FileSystemDirectoryHandle,
  sourceRelativePath: string,
  expectedChecksumSha256: string,
): Promise<void> {
  const handle = await sourceFileHandle(folder, sourceRelativePath);
  if ((await sha256(await handle.getFile())) !== expectedChecksumSha256) {
    throw new Error(
      'Plik w katalogu cut różni się od zdjęcia w stagingu. Podmiana została wstrzymana.',
    );
  }
}

export async function replacePageGeometryCutSource(
  folder: FileSystemDirectoryHandle,
  sourceRelativePath: string,
  expectedOldChecksumSha256: string,
  replacement: File,
): Promise<string> {
  const handle = await sourceFileHandle(folder, sourceRelativePath);
  const currentChecksum = await sha256(await handle.getFile());
  const replacementChecksum = await sha256(replacement);
  if (currentChecksum !== expectedOldChecksumSha256) {
    throw new Error(
      'Oryginał w katalogu cut zmienił się przed zapisem. Podmiana została wstrzymana.',
    );
  }
  if (replacementChecksum === currentChecksum) {
    throw new Error('Nowe zdjęcie jest identyczne z obecnym.');
  }
  const writable = await handle.createWritable();
  try {
    await writable.write(replacement);
    await writable.close();
  } catch (cause) {
    await writable.abort().catch(() => undefined);
    throw cause;
  }
  if ((await sha256(await handle.getFile())) !== replacementChecksum) {
    throw new Error('Nie udało się potwierdzić zapisu nowego zdjęcia w katalogu cut.');
  }
  return replacementChecksum;
}
