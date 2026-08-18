'use client';

export interface ManualImageFile {
  readonly handle: FileSystemFileHandle;
  readonly name: string;
  readonly relativePath: string;
}

export type ManualDecisionAction = 'accepted' | 'skipped';

export interface ManualSelectionDecision {
  readonly action: ManualDecisionAction;
  readonly imagePath: string | null;
  readonly imageChecksum: string | null;
  readonly outputName: string | null;
  readonly rangeEnd: number;
  readonly rangeStart: number;
}

export interface ManualSelectionState {
  readonly currentIndex: number;
  readonly decisions: readonly ManualSelectionDecision[];
  readonly direction: 'ascending' | 'descending';
  readonly firstLayout: number;
  readonly navigationStep?: number;
  readonly nextRangeStart: number;
  readonly updatedAt: string;
}

export interface ManualSelectionSessionRecord {
  readonly gameId: string;
  readonly key: string;
  readonly outputDirectory: FileSystemDirectoryHandle;
  readonly sourceDirectory: FileSystemDirectoryHandle;
  readonly sourceDirectoryName: string;
  readonly state: ManualSelectionState;
}

const JPEG_EXTENSIONS = new Set(['.jpg', '.jpeg']);
const NATURAL_PARTS = /(\d+)/g;

export function isSupportedManualImage(name: string): boolean {
  const extension = name.slice(name.lastIndexOf('.')).toLowerCase();
  return JPEG_EXTENSIONS.has(extension);
}

export async function listManualImages(
  directory: FileSystemDirectoryHandle,
): Promise<ManualImageFile[]> {
  const files: ManualImageFile[] = [];

  async function visit(
    current: FileSystemDirectoryHandle,
    prefix: string,
  ): Promise<void> {
    for await (const [name, entry] of current.entries()) {
      const relativePath = prefix === '' ? name : `${prefix}/${name}`;
      if (entry.kind === 'directory') {
        await visit(entry, relativePath);
        continue;
      }
      if (entry.kind !== 'file' || !isSupportedManualImage(name)) continue;
      files.push({
        handle: entry,
        name,
        relativePath,
      });
    }
  }

  await visit(directory, '');
  return files.sort((left, right) => {
    const pathOrder = naturalCompare(left.relativePath, right.relativePath);
    return pathOrder === 0
      ? left.relativePath.localeCompare(right.relativePath)
      : pathOrder;
  });
}

export function naturalCompare(left: string, right: string): number {
  const leftParts = left.toLocaleLowerCase().split(NATURAL_PARTS);
  const rightParts = right.toLocaleLowerCase().split(NATURAL_PARTS);
  const length = Math.max(leftParts.length, rightParts.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = leftParts[index] ?? '';
    const rightPart = rightParts[index] ?? '';
    const leftNumber = /^\d+$/.test(leftPart) ? Number(leftPart) : null;
    const rightNumber = /^\d+$/.test(rightPart) ? Number(rightPart) : null;
    if (
      leftNumber !== null &&
      rightNumber !== null &&
      leftNumber !== rightNumber
    ) {
      return leftNumber - rightNumber;
    }
    if (leftPart !== rightPart) return leftPart < rightPart ? -1 : 1;
  }
  return 0;
}

export function rangeForStart(rangeStart: number): {
  start: number;
  end: number;
} {
  return { end: rangeStart + 8, start: rangeStart };
}

export function createManualSelectionState(
  firstLayout: number,
  direction: 'ascending' | 'descending',
): ManualSelectionState {
  return {
    currentIndex: 0,
    decisions: [],
    direction,
    firstLayout,
    navigationStep: 1,
    nextRangeStart: firstLayout,
    updatedAt: new Date().toISOString(),
  };
}

export function nextManualSelectionState(
  state: ManualSelectionState,
  decision: ManualSelectionDecision,
  currentIndex: number,
): ManualSelectionState {
  return {
    ...state,
    currentIndex,
    decisions: [...state.decisions, decision],
    nextRangeStart: state.nextRangeStart + 9,
    updatedAt: new Date().toISOString(),
  };
}

export function previousManualSelectionState(
  state: ManualSelectionState,
): ManualSelectionState | null {
  const last = state.decisions.at(-1);
  if (last === undefined) return null;
  return {
    ...state,
    currentIndex: state.currentIndex,
    decisions: state.decisions.slice(0, -1),
    nextRangeStart: last.rangeStart,
    updatedAt: new Date().toISOString(),
  };
}

export async function sha256Hex(value: Blob): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await value.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export interface ManualOutputFileResult {
  readonly checksum: string;
  readonly created: boolean;
  readonly name: string;
}

export async function writeManualOutput(
  outputDirectory: FileSystemDirectoryHandle,
  source: ManualImageFile,
  rangeStart: number,
  rangeEnd: number,
  options: { readonly allowReplace?: boolean } = {},
): Promise<ManualOutputFileResult> {
  const sourceFile = await source.handle.getFile();
  const checksum = await sha256Hex(sourceFile);
  const name = `seq_${rangeStart}-${rangeEnd}.jpg`;
  let existing: File | null = null;
  try {
    existing = await (await outputDirectory.getFileHandle(name)).getFile();
  } catch (error) {
    if (!(error instanceof DOMException) || error.name !== 'NotFoundError')
      throw error;
  }
  if (existing !== null) {
    const existingChecksum = await sha256Hex(existing);
    if (existingChecksum === checksum)
      return { checksum, created: false, name };
    if (!options.allowReplace) {
      throw new Error(`Plik ${name} już istnieje i ma inną zawartość.`);
    }
  }
  const target = await outputDirectory.getFileHandle(name, { create: true });
  const writable = await target.createWritable();
  try {
    await writable.write(sourceFile);
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => undefined);
    throw error;
  }
  const written = await target.getFile();
  const writtenChecksum = await sha256Hex(written);
  if (writtenChecksum !== checksum) {
    throw new Error(`Weryfikacja zapisu pliku ${name} nie powiodła się.`);
  }
  return { checksum, created: true, name };
}

export async function removeManagedManualOutput(
  outputDirectory: FileSystemDirectoryHandle,
  decision: ManualSelectionDecision,
): Promise<void> {
  if (decision.outputName === null || decision.imageChecksum === null) return;
  const target = await outputDirectory.getFileHandle(decision.outputName);
  const existingChecksum = await sha256Hex(await target.getFile());
  if (existingChecksum !== decision.imageChecksum) {
    throw new Error(`Nie usuwam obcego pliku ${decision.outputName}.`);
  }
  await outputDirectory.removeEntry(decision.outputName);
}
