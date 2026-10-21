import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { SelectorError } from '../contracts.ts';
import { isManualSelectionRangeTerminal } from '@game-predictor/manual-image-selection-core';
import {
  SecureFiles,
  assertSeparateRoots,
  canonicalDirectoryLocation,
  checksum,
  stableStringify,
} from '../filesystem/secure-files.ts';
import { OUTPUT_MANIFEST_NAME } from '../manifest/operator-local.ts';
import { inventoryFor } from '../project/project-store.ts';
import { validateState } from '../project/state-codec.ts';
import type {
  ProjectAdoptionSeed,
  ProjectDecision,
  ProjectState,
} from '../project/types.ts';

export interface LegacyProof {
  sourceRoot: string;
  oldOutputRoot: string;
  manifestChecksum: string;
  seed: ProjectAdoptionSeed;
  schemaVersion: 1 | 2;
  legacyCursor: boolean;
}
const fields = new Set([
  'schemaVersion',
  'storageMode',
  'sessionId',
  'batchId',
  'sourceDirectoryName',
  'sourceManifestChecksumSha256',
  'fileCount',
  'firstLayout',
  'direction',
  'sourceTraversalSemantics',
  'sequenceUpperBound',
  'selectionComplete',
  'decisions',
  'currentIndex',
  'nextRangeStart',
  'updatedAt',
]);
const decisionFields = new Set([
  'action',
  'operationId',
  'fileId',
  'sourceIndex',
  'imagePath',
  'imageChecksumSha256',
  'outputName',
  'rangeStart',
  'rangeEnd',
  'selectionGeneration',
  'activeBoardCount',
]);
function fail(message: string, code = 'LEGACY_INVALID'): never {
  throw new SelectorError(code, message);
}
/** Read-only, full byte proof. Browser metadata differences are never guessed. */
export async function inspectLegacy(
  sourceRoot: string,
  oldOutputRoot: string,
): Promise<LegacyProof> {
  const source = await inventoryFor(sourceRoot);
  const output = new SecureFiles(
    await canonicalDirectoryLocation(oldOutputRoot),
  );
  await output.verifyRoot();
  assertSeparateRoots([source.root, output.root]);
  const bytes = await output.read(OUTPUT_MANIFEST_NAME);
  if (!bytes)
    fail('Brakuje manifestu sesji Reviewera.', 'LEGACY_MISSING_PROOF');
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(bytes.toString());
  } catch {
    fail('Manifest sesji jest uszkodzony.');
  }
  if (
    !raw ||
    typeof raw !== 'object' ||
    Array.isArray(raw) ||
    (raw.schemaVersion !== 1 && raw.schemaVersion !== 2) ||
    raw.storageMode !== 'operator_local' ||
    Object.keys(raw).some((key) => !fields.has(key))
  )
    fail(
      'Obsługiwany jest wyłącznie manifest operator-local v1 lub v2.',
      'LEGACY_UNSUPPORTED',
    );
  if (
    typeof raw.sourceManifestChecksumSha256 !== 'string' ||
    !/^[a-f0-9]{64}$/.test(raw.sourceManifestChecksumSha256) ||
    !Number.isSafeInteger(raw.fileCount) ||
    !Number.isSafeInteger(raw.firstLayout) ||
    !['ascending', 'descending'].includes(String(raw.direction))
  )
    fail(
      'Manifest nie zawiera pełnego dowodu źródła i jawnej konfiguracji.',
      'LEGACY_MISSING_PROOF',
    );
  if (
    raw.sourceManifestChecksumSha256 !== source.checksum ||
    raw.fileCount !== source.inventory.length ||
    raw.sourceDirectoryName !== path.basename(source.root)
  )
    fail(
      'Źródło nie odpowiada manifestowi. Nazwy, daty, rozmiary lub typy plików różnią się; zgodność nie jest zgadywana.',
      'LEGACY_SOURCE_CONFLICT',
    );
  if (
    !source.inventory.length ||
    typeof raw.sessionId !== 'string' ||
    !raw.sessionId ||
    typeof raw.batchId !== 'string' ||
    !raw.batchId ||
    typeof raw.updatedAt !== 'string' ||
    !Number.isFinite(Date.parse(raw.updatedAt)) ||
    !Number.isSafeInteger(raw.currentIndex) ||
    Number(raw.currentIndex) < 0 ||
    Number(raw.currentIndex) >= source.inventory.length ||
    (raw.sourceTraversalSemantics !== undefined &&
      raw.sourceTraversalSemantics !== 'natural_v2') ||
    !Array.isArray(raw.decisions)
  )
    fail('Manifest ma nieprawidłową pozycję lub historię.');
  if (
    raw.schemaVersion === 1 &&
    (raw.sequenceUpperBound !== undefined ||
      raw.selectionComplete !== undefined)
  )
    fail('Manifest v1 zawiera niejednoznaczną konfigurację.');
  if (
    raw.schemaVersion === 2 &&
    (!('sequenceUpperBound' in raw) ||
      typeof raw.selectionComplete !== 'boolean' ||
      (raw.sequenceUpperBound !== null &&
        (!Number.isSafeInteger(raw.sequenceUpperBound) ||
          Number(raw.sequenceUpperBound) < Number(raw.firstLayout))))
  )
    fail('Nieprawidłowa granica plansz v2.');
  const decisions: ProjectDecision[] = raw.decisions.map((value: unknown) => {
    if (
      !value ||
      typeof value !== 'object' ||
      Array.isArray(value) ||
      Object.keys(value).some((key) => !decisionFields.has(key))
    )
      fail('Nieprawidłowa decyzja w historii.');
    const d = value as ProjectDecision;
    if (
      raw.schemaVersion === 2 &&
      d.activeBoardCount !== d.rangeEnd - d.rangeStart + 1
    )
      fail('Nieprawidłowa liczba plansz w decyzji.');
    if (raw.schemaVersion === 1 && d.rangeEnd !== d.rangeStart + 8)
      fail('Nieprawidłowy zakres v1.');
    return { ...d, activeBoardCount: d.rangeEnd - d.rangeStart + 1 };
  });
  const acceptedPaths = decisions
    .filter((d) => d.action === 'accepted')
    .map((d) => d.imagePath);
  if (new Set(acceptedPaths).size !== acceptedPaths.length)
    fail(
      'Historia ponownie akceptuje to samo zdjęcie. Ta nietypowa historia nie jest zgodna z projektem desktopowym.',
      'LEGACY_UNSUPPORTED_HISTORY',
    );
  const legacyCursor =
    raw.direction === 'descending' &&
    raw.sourceTraversalSemantics !== 'natural_v2';
  const lastAccepted = [...decisions]
    .reverse()
    .find((d) => d.action === 'accepted');
  const cursor = legacyCursor
    ? Math.min(
        (lastAccepted?.sourceIndex ?? -1) + 1,
        source.inventory.length - 1,
      )
    : Number(raw.currentIndex);
  const seed: ProjectAdoptionSeed = {
    inventory: source.inventory,
    sourceDirectoryName: path.basename(source.root),
    sourceManifestChecksumSha256: source.checksum,
    firstLayout: Number(raw.firstLayout),
    direction: raw.direction as 'ascending' | 'descending',
    sequenceUpperBound:
      raw.schemaVersion === 2
        ? (raw.sequenceUpperBound as number | null)
        : null,
    currentRelativePath: source.inventory[cursor]?.relativePath ?? null,
    nextRangeStart: Number(raw.nextRangeStart),
    selectionComplete:
      raw.schemaVersion === 2 ? (raw.selectionComplete as boolean) : false,
    selectionGeneration: decisions.reduce(
      (generation, d) => Math.max(generation, d.selectionGeneration),
      0,
    ),
    decisions,
  };
  const state: ProjectState = {
    ...seed,
    schemaVersion: 1,
    projectId: randomUUID(),
    revision: 0,
    sourceRoot: source.root,
    outputRoot: output.root,
    receipts: {},
    updatedAt: raw.updatedAt,
  };
  try {
    const last = state.decisions.at(-1);
    if (
      raw.schemaVersion === 1 &&
      last &&
      isManualSelectionRangeTerminal(
        state.direction,
        last.rangeStart,
        last.rangeEnd,
        state.sequenceUpperBound,
      ) !== state.selectionComplete
    )
      throw new Error('Legacy v1 has no explicit completion state.');
    validateState(state);
  } catch {
    fail(
      'Historia lub stan zakończenia nie mają równoważnego stanu w projekcie desktopowym.',
      'LEGACY_STATE_CONFLICT',
    );
  }
  const expected = new Set([
    OUTPUT_MANIFEST_NAME,
    ...decisions
      .filter((d) => d.action === 'accepted')
      .map((d) => d.outputName!),
  ]);
  const names = await output.names(true);
  if (
    names.length !== expected.size ||
    names.some((name) => !expected.has(name))
  )
    fail(
      'Stary wynik zawiera obce pliki albo brakuje zapisanego JPEG-a.',
      'LEGACY_OUTPUT_CONFLICT',
    );
  const sourceFiles = new SecureFiles(source.root);
  await sourceFiles.verifyRoot();
  for (const d of decisions) {
    if (d.action !== 'accepted') continue;
    if (
      (await output.hash(d.outputName!)) !== d.imageChecksumSha256 ||
      (await sourceFiles.hash(d.imagePath!)) !== d.imageChecksumSha256
    )
      fail(
        'JPEG źródłowy lub wynikowy nie odpowiada zapisanej sumie kontrolnej.',
        'LEGACY_CHECKSUM_CONFLICT',
      );
  }
  // Recheck metadata and manifest after potentially long streaming hashes.
  const after = await inventoryFor(source.root);
  if (
    after.checksum !== source.checksum ||
    checksum((await output.read(OUTPUT_MANIFEST_NAME))!) !== checksum(bytes) ||
    stableStringify((await output.names()).sort()) !==
      stableStringify(names.sort())
  )
    fail(
      'Sesja zmieniła się podczas podglądu. Wybierz ją ponownie.',
      'LEGACY_CHANGED',
    );
  return {
    sourceRoot: source.root,
    oldOutputRoot: output.root,
    manifestChecksum: checksum(bytes),
    seed,
    schemaVersion: raw.schemaVersion,
    legacyCursor,
  };
}
export function sameLegacyProof(
  before: LegacyProof,
  after: LegacyProof,
): boolean {
  return stableStringify(before) === stableStringify(after);
}
