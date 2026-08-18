import type {
  GameResponse,
  JobResponse,
  OperationalImageReviewCountsResponse,
  OperationalImageReviewItemResponse,
  OperationalImageReviewGeometryCommand,
  OperationalImageReviewGeometryPoint,
  OperationalImageReviewGeometryPreviewCommand,
  OperationalImageReviewResolutionCommand,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

const OPERATIONAL_REVIEW_SHORTCUT_KEYS = [
  '1',
  '2',
  '3',
  '4',
  '5',
  '6',
  '7',
  '8',
  '9',
  '0',
  ...'qwertyuiopasdfghjklzxcvbnm',
] as const;

export interface OperationalReviewSymbolShortcut {
  readonly key: string | null;
  readonly symbol: SymbolResponse;
}

export type OperationalReviewKeyboardAction =
  | { readonly type: 'none' }
  | { readonly type: 'previous' }
  | { readonly symbolCode: string; readonly type: 'set-symbol' }
  | { readonly type: 'submit' };

export interface OperationalReviewKeyboardInput {
  readonly hasPrevious: boolean;
  readonly key: string;
  readonly otherDialogOpen: boolean;
  readonly repeat: boolean;
  readonly saving: boolean;
  readonly shortcuts: readonly OperationalReviewSymbolShortcut[];
  readonly typingTarget: boolean;
}

export function orderOperationalReviewGames(
  games: readonly GameResponse[],
): readonly GameResponse[] {
  return [...games].sort(
    (left, right) =>
      left.name.localeCompare(right.name, 'pl') ||
      left.code.localeCompare(right.code),
  );
}

export function isImageImportJob(job: JobResponse): boolean {
  return (
    job.jobType === 'import' &&
    'importKind' in job.inputPayload &&
    job.inputPayload.importKind === 'image_directory'
  );
}

export function orderOperationalReviewJobs(
  jobs: readonly JobResponse[],
): readonly JobResponse[] {
  return [...jobs].sort(
    (left, right) =>
      Date.parse(right.createdAt) - Date.parse(left.createdAt) ||
      right.id.localeCompare(left.id),
  );
}

export function operationalReviewStatusLabel(status: string): string {
  const labels: Readonly<Record<string, string>> = {
    accepted: 'Zaakceptowana',
    corrected: 'Poprawiona',
    pending: 'Do weryfikacji',
    rejected: 'Odrzucona',
  };
  return labels[status] ?? `Nieznany status: ${status}`;
}

export function updateOperationalReviewCounts(
  counts: OperationalImageReviewCountsResponse,
  previousStatus: string | undefined,
  nextStatus: string,
): OperationalImageReviewCountsResponse {
  if (previousStatus === undefined || previousStatus === nextStatus) {
    return counts;
  }
  let pending = counts.pending;
  let accepted = counts.accepted;
  let corrected = counts.corrected;
  let rejected = counts.rejected;

  if (previousStatus === 'pending') pending = Math.max(0, pending - 1);
  if (previousStatus === 'accepted') accepted = Math.max(0, accepted - 1);
  if (previousStatus === 'corrected') corrected = Math.max(0, corrected - 1);
  if (previousStatus === 'rejected') rejected = Math.max(0, rejected - 1);

  if (nextStatus === 'pending') pending += 1;
  if (nextStatus === 'accepted') accepted += 1;
  if (nextStatus === 'corrected') corrected += 1;
  if (nextStatus === 'rejected') rejected += 1;

  return {
    accepted,
    completed: accepted + corrected,
    corrected,
    pending,
    rejected,
    total: counts.total,
  };
}

export function operationalReviewSequence(
  item: OperationalImageReviewItemResponse,
): number | null {
  return item.sequenceNumber ?? item.suggestedSequenceNumber ?? null;
}

export function orderOperationalReviewSymbols(
  symbols: readonly SymbolResponse[],
): readonly SymbolResponse[] {
  return [...symbols]
    .filter((symbol) => symbol.status === 'active')
    .sort(
      (left, right) =>
        left.displayOrder - right.displayOrder ||
        left.mobileCode - right.mobileCode ||
        left.code.localeCompare(right.code),
    );
}

export function buildOperationalReviewSymbolShortcuts(
  symbols: readonly SymbolResponse[],
): readonly OperationalReviewSymbolShortcut[] {
  return orderOperationalReviewSymbols(symbols).map((symbol, index) => ({
    key: OPERATIONAL_REVIEW_SHORTCUT_KEYS[index] ?? null,
    symbol,
  }));
}

export function operationalReviewSymbolForKey(
  shortcuts: readonly OperationalReviewSymbolShortcut[],
  key: string,
): SymbolResponse | null {
  const normalized = key.toLocaleLowerCase('en-US');
  return (
    shortcuts.find((shortcut) => shortcut.key === normalized)?.symbol ?? null
  );
}

export function isOperationalReviewTypingTarget(target: unknown): boolean {
  if (typeof target !== 'object' || target === null) return false;
  const candidate = target as {
    readonly isContentEditable?: boolean;
    readonly tagName?: unknown;
  };
  if (candidate.isContentEditable === true) return true;
  if (typeof candidate.tagName !== 'string') return false;
  return ['INPUT', 'SELECT', 'TEXTAREA'].includes(
    candidate.tagName.toLocaleUpperCase('en-US'),
  );
}

export function operationalReviewKeyboardAction(
  input: OperationalReviewKeyboardInput,
): OperationalReviewKeyboardAction {
  if (input.saving || input.repeat || input.typingTarget) {
    return { type: 'none' };
  }
  if (input.otherDialogOpen) return { type: 'none' };
  if (input.key === 'ArrowLeft' && input.hasPrevious) {
    return { type: 'previous' };
  }
  if (input.key === 'ArrowRight' || input.key === 'Enter') {
    return { type: 'submit' };
  }
  const symbol = operationalReviewSymbolForKey(input.shortcuts, input.key);
  return symbol === null
    ? { type: 'none' }
    : { symbolCode: symbol.code, type: 'set-symbol' };
}

export function operationalReviewDraftSymbols(
  item: OperationalImageReviewItemResponse,
): readonly string[] {
  return item.cells.map((cell) => cell.currentSymbolCode);
}

export type OperationalReviewGeometryCorners = [
  OperationalImageReviewGeometryPoint,
  OperationalImageReviewGeometryPoint,
  OperationalImageReviewGeometryPoint,
  OperationalImageReviewGeometryPoint,
];

export interface OperationalReviewGeometryViewport {
  readonly height: number;
  readonly width: number;
  readonly x: number;
  readonly y: number;
}

export interface OperationalReviewCanvasPointer {
  readonly point: OperationalImageReviewGeometryPoint;
  readonly scale: number;
}

export function operationalReviewPointInCanvas(
  clientPoint: OperationalImageReviewGeometryPoint,
  bounds: {
    readonly height: number;
    readonly left: number;
    readonly top: number;
    readonly width: number;
  },
  canvasWidth: number,
  canvasHeight: number,
): OperationalReviewCanvasPointer {
  const safeCanvasWidth = Math.max(1, canvasWidth);
  const safeCanvasHeight = Math.max(1, canvasHeight);
  const safeBoundsWidth = Math.max(1, bounds.width);
  const safeBoundsHeight = Math.max(1, bounds.height);
  const scale = Math.max(
    Number.EPSILON,
    Math.min(
      safeBoundsWidth / safeCanvasWidth,
      safeBoundsHeight / safeCanvasHeight,
    ),
  );
  const renderedWidth = safeCanvasWidth * scale;
  const renderedHeight = safeCanvasHeight * scale;
  const contentLeft = bounds.left + (safeBoundsWidth - renderedWidth) / 2;
  const contentTop = bounds.top + (safeBoundsHeight - renderedHeight) / 2;
  return {
    point: {
      x: Math.min(
        safeCanvasWidth,
        Math.max(0, (clientPoint.x - contentLeft) / scale),
      ),
      y: Math.min(
        safeCanvasHeight,
        Math.max(0, (clientPoint.y - contentTop) / scale),
      ),
    },
    scale,
  };
}

export function operationalReviewGeometryCorners(
  item: OperationalImageReviewItemResponse,
  imageWidth: number,
  imageHeight: number,
): OperationalReviewGeometryCorners {
  const geometry = item.geometry;
  const raw =
    geometry.sourceQuad ?? geometry.quad ?? geometry.corners ?? undefined;
  if (Array.isArray(raw) && raw.length === 4) {
    const parsed = raw.map(parseGeometryPoint);
    if (parsed.every((point) => point !== null)) {
      return parsed as unknown as OperationalReviewGeometryCorners;
    }
  }
  const insetX = Math.max(1, Math.round(imageWidth * 0.1));
  const insetY = Math.max(1, Math.round(imageHeight * 0.1));
  return [
    { x: insetX, y: insetY },
    { x: imageWidth - insetX - 1, y: insetY },
    { x: imageWidth - insetX - 1, y: imageHeight - insetY - 1 },
    { x: insetX, y: imageHeight - insetY - 1 },
  ];
}

export function operationalReviewGeometryViewport(
  corners: OperationalReviewGeometryCorners,
  imageWidth: number,
  imageHeight: number,
  paddingRatio = 0.25,
): OperationalReviewGeometryViewport {
  const boundedWidth = Math.max(1, Math.round(imageWidth));
  const boundedHeight = Math.max(1, Math.round(imageHeight));
  const xs = corners.map((point) =>
    Math.min(boundedWidth - 1, Math.max(0, point.x)),
  );
  const ys = corners.map((point) =>
    Math.min(boundedHeight - 1, Math.max(0, point.y)),
  );
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const boardWidth = Math.max(1, maxX - minX);
  const boardHeight = Math.max(1, maxY - minY);
  const paddingX = Math.max(16, Math.round(boardWidth * paddingRatio));
  const paddingY = Math.max(16, Math.round(boardHeight * paddingRatio));
  const x = Math.max(0, Math.floor(minX - paddingX));
  const y = Math.max(0, Math.floor(minY - paddingY));
  const right = Math.min(boundedWidth, Math.ceil(maxX + paddingX));
  const bottom = Math.min(boundedHeight, Math.ceil(maxY + paddingY));
  return {
    height: Math.max(1, bottom - y),
    width: Math.max(1, right - x),
    x,
    y,
  };
}

export function operationalReviewNativeContextViewport(
  item: OperationalImageReviewItemResponse,
  imageWidth: number,
  imageHeight: number,
): OperationalReviewGeometryViewport {
  const boundedWidth = Math.max(1, Math.round(imageWidth));
  const boundedHeight = Math.max(1, Math.round(imageHeight));
  const retainedViewport = parseGeometryViewport(
    item.geometry.sourceContextBounds,
    boundedWidth,
    boundedHeight,
  );
  if (retainedViewport !== null) return retainedViewport;
  const board = operationalReviewGeometryCorners(
    item,
    boundedWidth,
    boundedHeight,
  );
  const rawLabel = item.geometry.sequenceLabelQuad;
  const parsedLabel = Array.isArray(rawLabel)
    ? rawLabel.map(parseGeometryPoint)
    : [];
  const hasLabel =
    parsedLabel.length === 4 && parsedLabel.every((point) => point !== null);
  const label = hasLabel
    ? (parsedLabel as OperationalImageReviewGeometryPoint[])
    : [];
  const points = [...board, ...label];
  const xs = points.map((point) =>
    Math.min(boundedWidth - 1, Math.max(0, point.x)),
  );
  const ys = points.map((point) =>
    Math.min(boundedHeight - 1, Math.max(0, point.y)),
  );
  const boardXs = board.map((point) => point.x);
  const boardYs = board.map((point) => point.y);
  const boardWidth = Math.max(1, Math.max(...boardXs) - Math.min(...boardXs));
  const boardHeight = Math.max(1, Math.max(...boardYs) - Math.min(...boardYs));
  const horizontalPadding = Math.max(12, Math.round(boardWidth * 0.1));
  const topPadding = Math.max(12, Math.round(boardHeight * 0.12));
  const bottomPadding = Math.max(
    12,
    Math.round(boardHeight * (hasLabel ? 0.12 : 0.55)),
  );
  const x = Math.max(0, Math.floor(Math.min(...xs) - horizontalPadding));
  const y = Math.max(0, Math.floor(Math.min(...ys) - topPadding));
  const right = Math.min(
    boundedWidth,
    Math.ceil(Math.max(...xs) + horizontalPadding),
  );
  const bottom = Math.min(
    boundedHeight,
    Math.ceil(Math.max(...ys) + bottomPadding),
  );
  return {
    height: Math.max(1, bottom - y),
    width: Math.max(1, right - x),
    x,
    y,
  };
}

export function operationalReviewPointInGeometryViewport(
  point: OperationalImageReviewGeometryPoint,
  viewport: OperationalReviewGeometryViewport,
): OperationalImageReviewGeometryPoint {
  return { x: point.x - viewport.x, y: point.y - viewport.y };
}

export function operationalReviewPointInSourceImage(
  point: OperationalImageReviewGeometryPoint,
  viewport: OperationalReviewGeometryViewport,
  imageWidth: number,
  imageHeight: number,
): OperationalImageReviewGeometryPoint {
  return clampOperationalReviewGeometryPoint(
    { x: point.x + viewport.x, y: point.y + viewport.y },
    imageWidth,
    imageHeight,
  );
}

export function buildOperationalReviewGeometryPreviewCommand(
  item: OperationalImageReviewItemResponse,
  corners: OperationalReviewGeometryCorners,
): OperationalImageReviewGeometryPreviewCommand {
  return {
    corners,
    expectedGeometryRevision: item.geometryRevision,
    expectedResolutionRevision: item.resolutionRevision,
  };
}

export function buildOperationalReviewGeometryCommand(
  item: OperationalImageReviewItemResponse,
  corners: OperationalReviewGeometryCorners,
  idempotencyKey: string,
): OperationalImageReviewGeometryCommand {
  return {
    ...buildOperationalReviewGeometryPreviewCommand(item, corners),
    correctedBy: 'local-admin',
    idempotencyKey,
  };
}

export function clampOperationalReviewGeometryPoint(
  point: OperationalImageReviewGeometryPoint,
  imageWidth: number,
  imageHeight: number,
): OperationalImageReviewGeometryPoint {
  return {
    x: Math.min(imageWidth - 1, Math.max(0, Math.round(point.x))),
    y: Math.min(imageHeight - 1, Math.max(0, Math.round(point.y))),
  };
}

function parseGeometryPoint(
  value: unknown,
): OperationalImageReviewGeometryPoint | null {
  if (Array.isArray(value) && value.length === 2) {
    const [x, y] = value;
    return isNonNegativeFiniteNumber(x) && isNonNegativeFiniteNumber(y)
      ? { x: Math.round(x), y: Math.round(y) }
      : null;
  }
  if (typeof value !== 'object' || value === null) return null;
  const candidate = value as { readonly x?: unknown; readonly y?: unknown };
  return isNonNegativeFiniteNumber(candidate.x) &&
    isNonNegativeFiniteNumber(candidate.y)
    ? { x: Math.round(candidate.x), y: Math.round(candidate.y) }
    : null;
}

function isNonNegativeFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

export function isOperationalReviewDraftChangedFromCurrent(
  item: OperationalImageReviewItemResponse,
  sequenceNumber: number,
  symbolCodes: readonly string[],
): boolean {
  return (
    sequenceNumber !== operationalReviewSequence(item) ||
    item.cells.some(
      (cell, index) => cell.currentSymbolCode !== symbolCodes[index],
    )
  );
}

export function operationalReviewResolutionAction(
  item: OperationalImageReviewItemResponse,
  sequenceNumber: number,
  symbolCodes: readonly string[],
): 'accepted' | 'corrected' {
  const preservesPrediction =
    item.suggestedSequenceNumber === sequenceNumber &&
    item.cells.every(
      (cell, index) => cell.predictedSymbolCode === symbolCodes[index],
    );
  return preservesPrediction ? 'accepted' : 'corrected';
}

export function buildOperationalReviewResolutionCommand(
  item: OperationalImageReviewItemResponse,
  sequenceNumber: number,
  symbolCodes: readonly string[],
  idempotencyKey: string,
): OperationalImageReviewResolutionCommand {
  if (
    !Number.isInteger(sequenceNumber) ||
    sequenceNumber <= 0 ||
    symbolCodes.length !== 15 ||
    item.cells.length !== 15
  ) {
    throw new RangeError(
      'Operational review resolution requires a positive sequence and 15 cells.',
    );
  }
  return {
    action: operationalReviewResolutionAction(
      item,
      sequenceNumber,
      symbolCodes,
    ),
    cells: item.cells.map((cell, index) => ({
      cellIndex: cell.cellIndex,
      cropSampleId: cell.cropSampleId,
      symbolCode: requireSymbolCode(symbolCodes[index]),
    })),
    expectedRevision: item.resolutionRevision,
    geometryRevision: item.geometryRevision,
    idempotencyKey,
    resolvedBy: 'local-admin',
    sequenceNumber,
  };
}

export function formatOperationalConfidence(value: number): string {
  if (!Number.isFinite(value)) return 'Nieprawidłowa wartość';
  const bounded = Math.min(1, Math.max(0, value));
  return `${(bounded * 100).toLocaleString('pl-PL', {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
  })}%`;
}

export type OperationalReviewAssetKind = 'board' | 'cell' | 'source';

export function operationalReviewAssetUrl(
  apiBaseUrl: string,
  context: { readonly gameId: string; readonly importJobId: string },
  reviewItemId: string,
  asset: OperationalReviewAssetKind,
  options: {
    readonly cellIndex?: number;
    readonly usage?: string;
    readonly version?: string;
  } = {},
): string {
  const base = apiBaseUrl.endsWith('/') ? apiBaseUrl : `${apiBaseUrl}/`;
  const encodedItemId = encodeURIComponent(reviewItemId);
  const suffix =
    asset === 'cell' ? `cells/${requireCellIndex(options.cellIndex)}` : asset;
  const assetPath = `api/v1/admin/image-review-items/${encodedItemId}/assets/${suffix}`;
  if (base.startsWith('/')) {
    const query = new URLSearchParams({
      gameId: context.gameId,
      importJobId: context.importJobId,
    });
    if (options.version !== undefined) query.set('v', options.version);
    if (options.usage !== undefined) query.set('usage', options.usage);
    return `${base}${assetPath}?${query.toString()}`;
  }
  const url = new URL(assetPath, base);
  url.searchParams.set('gameId', context.gameId);
  url.searchParams.set('importJobId', context.importJobId);
  if (options.version !== undefined) {
    url.searchParams.set('v', options.version);
  }
  if (options.usage !== undefined) {
    url.searchParams.set('usage', options.usage);
  }
  return url.toString();
}

function parseGeometryViewport(
  value: unknown,
  imageWidth: number,
  imageHeight: number,
): OperationalReviewGeometryViewport | null {
  if (typeof value !== 'object' || value === null) return null;
  const candidate = value as {
    readonly height?: unknown;
    readonly width?: unknown;
    readonly x?: unknown;
    readonly y?: unknown;
  };
  if (
    !isNonNegativeFiniteNumber(candidate.x) ||
    !isNonNegativeFiniteNumber(candidate.y) ||
    !isNonNegativeFiniteNumber(candidate.width) ||
    !isNonNegativeFiniteNumber(candidate.height) ||
    candidate.width <= 0 ||
    candidate.height <= 0
  ) {
    return null;
  }
  const x = Math.min(imageWidth - 1, Math.round(candidate.x));
  const y = Math.min(imageHeight - 1, Math.round(candidate.y));
  const right = Math.min(imageWidth, x + Math.round(candidate.width));
  const bottom = Math.min(imageHeight, y + Math.round(candidate.height));
  return {
    height: Math.max(1, bottom - y),
    width: Math.max(1, right - x),
    x,
    y,
  };
}

export function operationalReviewJobLabel(job: JobResponse): string {
  const date = new Intl.DateTimeFormat('pl-PL', {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(job.createdAt));
  return `${date} · ${job.status} · ${job.id.slice(0, 8)}`;
}

function requireCellIndex(cellIndex: number | undefined): number {
  if (
    cellIndex === undefined ||
    !Number.isInteger(cellIndex) ||
    cellIndex < 0 ||
    cellIndex >= 15
  ) {
    throw new RangeError(
      'Operational review cell index must be between 0 and 14.',
    );
  }
  return cellIndex;
}

function requireSymbolCode(symbolCode: string | undefined): string {
  if (symbolCode === undefined || symbolCode.trim() === '') {
    throw new RangeError('Every operational review cell needs a symbol code.');
  }
  return symbolCode;
}
