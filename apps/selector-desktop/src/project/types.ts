export interface SourceInventoryItem {
  relativePath: string;
  name: string;
  sizeBytes: number;
  lastModifiedMs: number;
  mimeType: string;
}
export interface ProjectDecision {
  action: 'accepted' | 'skipped';
  operationId: string;
  fileId: string | null;
  sourceIndex: number;
  imagePath: string | null;
  imageChecksumSha256: string | null;
  outputName: string | null;
  rangeStart: number;
  rangeEnd: number;
  selectionGeneration: number;
  activeBoardCount: number;
}
export type ProjectCommand =
  | { kind: 'accept'; imagePath: string }
  | { kind: 'skip' }
  | { kind: 'navigate'; imagePath: string }
  | { kind: 'range'; start: number }
  | { kind: 'undo' }
  | { kind: 'restart'; expectedRevision: number; previewChecksum: string }
  | { kind: 'relink'; sourceRoot?: string; outputRoot?: string };
export interface OperationReceipt {
  fingerprint: string;
  revision: number;
  currentRelativePath: string | null;
  nextRangeStart: number;
  selectionComplete: boolean;
  decisionCount: number;
}
export interface ProjectState {
  /** Optional display metadata; absent in older schema-1 projects. */
  gameName?: string;
  schemaVersion: 1;
  projectId: string;
  revision: number;
  sourceRoot: string;
  outputRoot: string;
  sourceDirectoryName: string;
  sourceManifestChecksumSha256: string;
  inventory: SourceInventoryItem[];
  firstLayout: number;
  direction: 'ascending' | 'descending';
  sequenceUpperBound: number | null;
  currentRelativePath: string | null;
  nextRangeStart: number;
  selectionComplete: boolean;
  selectionGeneration: number;
  decisions: ProjectDecision[];
  receipts: Record<string, OperationReceipt>;
  updatedAt: string;
}
export interface ProjectCreateOptions {
  gameName?: string;
  sourceRoot: string;
  projectRoot: string;
  outputRoot: string;
  firstLayout: number;
  direction: 'ascending' | 'descending';
  sequenceUpperBound?: number | null;
  /** Native dialog requires this explicit confirmation, alongside path checks. */
  localStorageConfirmed: boolean;
}
export type ProjectAdoptionSeed = Pick<
  ProjectState,
  | 'firstLayout'
  | 'direction'
  | 'sequenceUpperBound'
  | 'currentRelativePath'
  | 'nextRangeStart'
  | 'selectionComplete'
  | 'selectionGeneration'
  | 'decisions'
  | 'inventory'
  | 'sourceManifestChecksumSha256'
  | 'sourceDirectoryName'
>;
export interface JournalCopy {
  imagePath: string;
  outputName: string;
  checksumSha256: string;
  sizeBytes: number;
}
export interface RestartPreview {
  revision: number;
  checksum: string;
  acceptedFiles: number;
  decisions: number;
}
export interface ProjectJournal {
  schemaVersion: 1 | 2;
  projectId: string;
  phase: 'prepared' | 'jpeg_written' | 'committed';
  before: ProjectState | null;
  after: ProjectState;
  operationId: string;
  copy: JournalCopy | null;
  /** Version 2 is an initial adoption transaction, never a replay of accepts. */
  importCopies?: JournalCopy[];
  removals: { outputName: string; checksumSha256: string }[];
}
