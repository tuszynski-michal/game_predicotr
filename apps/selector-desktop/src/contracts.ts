export const APP_URL = 'selector://app/index.html';
export const MAX_SEQUENCE_NUMBER = 500000;
export const CHANNELS = {
  openLogs: 'selector:open-logs',
  create: 'selector:create',
  begin: 'selector:begin',
  open: 'selector:open',
  recent: 'selector:recent',
  games: 'selector:games',
  addGame: 'selector:add-game',
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
  fullscreenChanged: 'selector:fullscreen-changed',
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
  games(): Promise<NativeResult<string[]>>;
  addGame(name: string): Promise<NativeResult<string[]>>;
  begin(): Promise<NativeResult<StartSelectionResult | null>>;
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
  onFullscreenChanged(listener: (active: boolean) => void): () => void;
}
export interface LegacyPreviewSummary {
  projectName?: string;
  outputName?: string;
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
  sourceToken?: string;
  gameName?: string;
  gameUpdate: string;
  firstLayout: number;
  direction: 'ascending' | 'descending';
  sequenceUpperBound: number | null;
  customLocations: boolean;
  localStorageConfirmed: boolean;
}
export interface NewProjectDraft {
  sourceToken: string;
  sourceName: string;
  sourcePath: string;
  projectPath: string;
  outputParentPath: string;
}
export type StartSelectionResult =
  | { kind: 'new'; draft: NewProjectDraft }
  | { kind: 'legacy'; preview: LegacyPreviewSummary }
  | { kind: 'existing'; workspace: DesktopWorkspace };
export function validateGameName(value: unknown): string {
  if (
    typeof value !== 'string' ||
    !value.trim() ||
    value.trim().length > 80 ||
    /[\u0000-\u001f\u007f]/.test(value)
  )
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'Podaj nazwę gry (1–80 znaków).',
    );
  return value.trim();
}
export const GAME_UPDATE_PATTERN = '(?:z_)?a[0-9]+';
const gameUpdateExpression = new RegExp(`^(?:${GAME_UPDATE_PATTERN})$`);
export function isGameUpdate(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.trim() === value &&
    gameUpdateExpression.test(value)
  );
}
export function validateGameUpdate(value: unknown): string {
  if (!isGameUpdate(value))
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'Podaj aktualizację w formacie a1 lub z_a1 (litery a albo z_a i cyfry).',
    );
  return value;
}
/** The configured batch range labels its directory; individual JPEG names are separate. */
export function outputDirectoryName(
  options: Pick<
    CreateProjectRequest,
    'gameName' | 'gameUpdate' | 'firstLayout' | 'sequenceUpperBound'
  >,
): string {
  const game = validateGameName(options.gameName);
  const update = validateGameUpdate(options.gameUpdate);
  const end = options.sequenceUpperBound ?? MAX_SEQUENCE_NUMBER;
  if (
    !Number.isSafeInteger(options.firstLayout) ||
    options.firstLayout < 1 ||
    !Number.isSafeInteger(end) ||
    end < options.firstLayout ||
    end > MAX_SEQUENCE_NUMBER
  )
    throw new SelectorError('INVALID_ARGUMENT', 'Podaj zakres od 1 do 500000.');
  const name = `${game} ${update} ${options.firstLayout}-${end}`;
  if (/[<>:"/\\|?*]/.test(name))
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'Nazwa gry nie może zawierać znaków folderu Windows: < > : " / \\ | ? *.',
    );
  if (name.length > 255)
    throw new SelectorError(
      'INVALID_ARGUMENT',
      'Nazwa folderu jest za długa. Skróć nazwę gry lub aktualizację.',
    );
  return name;
}
export type DesktopCommand =
  | { kind: 'accept' | 'navigate'; imageId: string }
  | { kind: 'skip' | 'undo' }
  | { kind: 'range'; start: number; direction?: 'ascending' | 'descending' }
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
  gameName?: string;
  gameUpdate?: string;
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
