export const APP_URL = 'selector://app/index.html';
export const CHANNELS = {
  openLogs: 'selector:open-logs',
  create: 'selector:create',
  open: 'selector:open',
  recent: 'selector:recent',
  continue: 'selector:continue',
  snapshot: 'selector:snapshot',
  execute: 'selector:execute',
  resume: 'selector:resume',
  relink: 'selector:relink',
  restartPreview: 'selector:restart-preview',
  saveView: 'selector:save-view',
  close: 'selector:close',
  openOutput: 'selector:open-output',
  fullscreen: 'selector:fullscreen',
  legacyPreview: 'selector:legacy-preview',
  legacyAdopt: 'selector:legacy-adopt',
} as const;
export interface SourceImage {
  id: string;
  relativePath: string;
  name: string;
  size: number;
  lastModified: number;
  url: string;
}
export interface SourceIndex {
  id: string;
  name: string;
  images: SourceImage[];
}
export type NativeResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: { code: string; message: string } };
export interface SelectorBridge {
  legacyPreview(): Promise<NativeResult<LegacyPreviewSummary | null>>;
  legacyAdopt(
    previewToken: string,
  ): Promise<NativeResult<DesktopWorkspace | null>>;
  openLogs(): Promise<NativeResult<void>>;
  create(
    options: CreateProjectRequest,
  ): Promise<NativeResult<DesktopWorkspace | null>>;
  open(): Promise<NativeResult<DesktopWorkspace | null>>;
  recent(): Promise<NativeResult<RecentProjectSummary[]>>;
  continue(projectId: string): Promise<NativeResult<DesktopWorkspace>>;
  snapshot(): Promise<NativeResult<DesktopWorkspace | null>>;
  execute(request: ExecuteRequest): Promise<NativeResult<DesktopWorkspace>>;
  resume(): Promise<NativeResult<DesktopWorkspace>>;
  relink(
    kind: 'source' | 'output',
  ): Promise<NativeResult<DesktopWorkspace | null>>;
  restartPreview(): Promise<NativeResult<RestartSummary>>;
  saveView(
    projectId: string,
    view: ViewPreferences,
  ): Promise<NativeResult<void>>;
  close(): Promise<NativeResult<void>>;
  openOutput(): Promise<NativeResult<void>>;
  fullscreen(): Promise<NativeResult<boolean>>;
}
export interface LegacyPreviewSummary {
  previewToken: string;
  schemaVersion: 1 | 2;
  sourceName: string;
  oldOutputName: string;
  fileCount: number;
  firstLayout: number;
  direction: 'ascending' | 'descending';
  sequenceUpperBound: number | null;
  nextRangeStart: number;
  selectionComplete: boolean;
  currentPhoto: number;
  acceptedCount: number;
  skippedCount: number;
  legacyCursor: boolean;
}
export interface ViewPreferences {
  navigationStep: number;
  zoom: number;
  scrollX: number;
  scrollY: number;
}
export interface CreateProjectRequest {
  firstLayout: number;
  direction: 'ascending' | 'descending';
  sequenceUpperBound: number | null;
  customLocations: boolean;
  localStorageConfirmed: boolean;
}
export type DesktopCommand =
  | { kind: 'accept' | 'navigate'; imageId: string }
  | { kind: 'skip' | 'undo' }
  | { kind: 'range'; start: number }
  | { kind: 'restart'; expectedRevision: number; previewChecksum: string };
export interface ExecuteRequest {
  projectId: string;
  operationId: string;
  command: DesktopCommand;
}
export interface RestartSummary {
  revision: number;
  checksum: string;
  acceptedFiles: number;
  decisions: number;
}
export interface RecentProjectSummary {
  projectId: string;
  name: string;
  openedAt: string;
}
export interface DesktopWorkspace {
  projectId: string;
  revision: number;
  source: SourceIndex | null;
  sourceName: string;
  projectName: string;
  outputName: string;
  currentImageId: string | null;
  firstLayout: number;
  direction: 'ascending' | 'descending';
  sequenceUpperBound: number | null;
  nextRangeStart: number;
  selectionComplete: boolean;
  acceptedCount: number;
  skippedCount: number;
  acceptedImageIds: string[];
  decisionCount: number;
  issue: { code: string; message: string } | null;
  view: ViewPreferences;
}
export class SelectorError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}
export function validateNoArguments(args: unknown[]): void {
  if (args.length !== 0)
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'To polecenie nie przyjmuje argumentów.',
    );
}
export function validateSender(
  senderUrl: string,
  isMainFrame: boolean,
  isWindow: boolean,
): void {
  if (senderUrl !== APP_URL || !isMainFrame || !isWindow)
    throw new SelectorError(
      'UNTRUSTED_SENDER',
      'Niedozwolony nadawca polecenia.',
    );
}
export function parsePhotoUrl(raw: string): {
  sourceId: string;
  imageId: string;
} {
  const match = /^selector-photo:\/\/([a-f0-9-]{36})\/([a-f0-9-]{36})$/.exec(
    raw,
  );
  if (!match)
    throw new SelectorError(
      'INVALID_PHOTO_ID',
      'Niedozwolony identyfikator zdjęcia.',
    );
  return { sourceId: match[1], imageId: match[2] };
}
