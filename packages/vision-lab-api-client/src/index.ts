import {
  detectGeometry as detect,
  listSources as list,
  getAnnotations,
  saveAnnotation,
  saveFamily,
  freezeSplit,
  createBackup,
  getTimings,
  startTrainingRun,
  listTrainingRuns,
  getTrainingRun,
  cancelTrainingRun,
  retryTrainingRun,
  listSymbolLabels,
  listSymbolDictionaries,
  getSymbolDictionary,
  previewSymbolCrop,
  saveSymbolDecision,
  createSymbolBackup,
} from './generated/sdk.gen';
import type {
  AnnotationRequest,
  FamilyRequest,
  SplitRequest,
  BoardInput,
  PhotoReviewRequest,
  StartRunRequestInput,
  RunMutation,
} from './generated/types.gen';
import type {
  SaveSymbolDecisionData,
  PreviewSymbolCropData,
} from './generated/types.gen';
export type SymbolRequest = SaveSymbolDecisionData['body'];
export type SymbolCropRequest = PreviewSymbolCropData['body'];
export type {
  SymbolPage,
  SymbolRow,
  DictionaryPage,
  DictionaryView,
  DictionaryEntry,
  LabCropPreview,
  LabBoardPreview,
  LabQueuePreview,
  LabQueueItem,
  LabelCellsDecide,
  LabelBoardDecide,
  DbCropPreview,
  SymbolResult,
} from './generated/types.gen';
export type {
  GeometryResult,
  Source,
  AnnotationState,
  GeometryAnnotationOutput as GeometryAnnotation,
  AnnotationRequest,
  FamilyRequest,
  SplitRequest,
  TimingReport,
  PhotoReviewRequest,
  PhotoReview,
  StoredGeometryQualification,
  FrozenSplit,
  StartRunRequestInput as StartRunRequest,
  RunMutation,
  RunState,
  RunPage,
  PointOutput as Point,
} from './generated/types.gen';

const baseUrl = '/api/lab';
export async function symbolLabels(
  gameId?: string,
  sourceId?: string,
  offset = 0,
  readToken?: string,
) {
  return (
    await listSymbolLabels({
      baseUrl,
      query: {
        game_id: gameId,
        source_id: sourceId,
        offset,
        limit: 50,
        read_token: readToken,
      },
      throwOnError: true,
    })
  ).data;
}
export async function symbolDictionaries(
  gameId?: string,
  offset = 0,
  readToken?: string,
) {
  return (
    await listSymbolDictionaries({
      baseUrl,
      query: { game_id: gameId, offset, limit: 100, read_token: readToken },
      throwOnError: true,
    })
  ).data;
}
export async function symbolDictionary(gameId: string, version: number) {
  return (
    await getSymbolDictionary({
      baseUrl,
      path: { game_id: gameId, version },
      throwOnError: true,
    })
  ).data;
}
let symbolPreviewTail: Promise<void> = Promise.resolve();
export async function symbolCrop(body: SymbolCropRequest, timeoutMs = 60_000) {
  // The local annotation store allows one reader at a time. Release the slot
  // on both success and failure so a board and queue can refresh together.
  const previous = symbolPreviewTail;
  let release: () => void = () => {};
  symbolPreviewTail = new Promise<void>((resolve) => { release = resolve; });
  await previous;
  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_resolve, reject) => {
    timeoutId = setTimeout(() => {
      controller.abort();
      reject(new Error('SYMBOL_PREVIEW_TIMEOUT'));
    }, timeoutMs);
  });
  try {
    return (await Promise.race([
      previewSymbolCrop({ baseUrl, body, signal: controller.signal, throwOnError: true }),
      timeout,
    ])).data;
  } finally {
    if (timeoutId !== undefined) clearTimeout(timeoutId);
    release();
  }
}
export async function symbolBoard(
  body: Extract<SymbolCropRequest, { kind: 'lab_board' }>,
) {
  const preview = await symbolCrop(body);
  if (preview.kind !== 'lab_board')
    throw new Error('SYMBOL_BOARD_RESPONSE_INVALID');
  return preview;
}
export const SYMBOL_QUEUE_VIEW_SIZE = 500;
const SYMBOL_QUEUE_FETCH_SIZE = 30;

export async function symbolQueue(
  gameId: string,
  offset = 0,
  readToken?: string,
) {
  let token = readToken;
  let revision: number | undefined;
  let total: number | undefined;
  const items = [] as Extract<Awaited<ReturnType<typeof symbolCrop>>, { kind: 'lab_queue' }>['items'];
  while (items.length < SYMBOL_QUEUE_VIEW_SIZE) {
    const preview = await symbolCrop({
      kind: 'lab_queue',
      game_id: gameId,
      offset: offset + items.length,
      limit: Math.min(SYMBOL_QUEUE_FETCH_SIZE, SYMBOL_QUEUE_VIEW_SIZE - items.length),
      read_token: token,
    });
    if (preview.kind !== 'lab_queue')
      throw new Error('SYMBOL_QUEUE_RESPONSE_INVALID');
    if (revision !== undefined &&
      (preview.revision !== revision || preview.total !== total || preview.read_token !== token))
      throw new Error('SYMBOL_QUEUE_VIEW_CHANGED');
    token = preview.read_token;
    revision = preview.revision;
    total = preview.total;
    items.push(...preview.items);
    if (offset + items.length >= total || preview.items.length === 0) {
      if (offset + items.length < total)
        throw new Error('SYMBOL_QUEUE_INCOMPLETE');
      return { ...preview, items };
    }
  }
  return { kind: 'lab_queue' as const, items, total: total!, revision: revision!, read_token: token! };
}
export async function writeSymbol(body: SymbolRequest) {
  return (await saveSymbolDecision({ baseUrl, body, throwOnError: true })).data;
}
export async function backupSymbols() {
  return (await createSymbolBackup({ baseUrl, body: {}, throwOnError: true }))
    .data;
}
export async function listSources(offset = 0, game?: string) {
  const response = await list({
    baseUrl,
    query: { offset, limit: 24, game },
    throwOnError: true,
  });
  return response.data;
}
export async function detectGeometry(
  sourceId: string,
  columns: 3 | 5,
  runId?: string,
) {
  const response = await detect({
    baseUrl,
    body: {
      source_id: sourceId,
      topology: { columns, rows: 3 },
      ...(runId ? { run_id: runId } : {}),
    },
    throwOnError: true,
  });
  return response.data;
}
export async function previewGeometry(
  sourceId: string,
  columns: 3 | 5,
  board: BoardInput,
) {
  return (
    await detect({
      baseUrl,
      body: {
        source_id: sourceId,
        topology: { columns, rows: 3 },
        preview_board: board,
      },
      throwOnError: true,
    })
  ).data;
}
export function assetUrl(assetId: string) {
  return `${baseUrl}/assets/${encodeURIComponent(assetId)}`;
}

export async function readAnnotations() {
  return (await getAnnotations({ baseUrl, throwOnError: true })).data;
}
export async function writeAnnotation(body: AnnotationRequest) {
  return (await saveAnnotation({ baseUrl, body, throwOnError: true })).data;
}
export async function writePhotoReview(body: PhotoReviewRequest) {
  return (await saveAnnotation({ baseUrl, body, throwOnError: true })).data;
}
export async function writeFamily(body: FamilyRequest) {
  return (await saveFamily({ baseUrl, body, throwOnError: true })).data;
}
export async function freezeAnnotations(body: SplitRequest) {
  // Preserve policy, game map and cohort order: all bind the server's retry receipt.
  return (await freezeSplit({ baseUrl, body, throwOnError: true })).data;
}
export async function backupAnnotations() {
  return (await createBackup({ baseUrl, body: {}, throwOnError: true })).data;
}
export async function annotationTimings() {
  return (await getTimings({ baseUrl, throwOnError: true })).data;
}

export async function startRun(body: StartRunRequestInput) {
  return (await startTrainingRun({ baseUrl, body, throwOnError: true })).data;
}
export async function listRuns(offset = 0, limit = 24) {
  return (
    await listTrainingRuns({
      baseUrl,
      query: { offset, limit },
      throwOnError: true,
    })
  ).data;
}
export async function readRun(runId: string) {
  return (
    await getTrainingRun({
      baseUrl,
      path: { run_id: runId },
      throwOnError: true,
    })
  ).data;
}
export async function cancelRun(runId: string, body: RunMutation) {
  return (
    await cancelTrainingRun({
      baseUrl,
      path: { run_id: runId },
      body,
      throwOnError: true,
    })
  ).data;
}
export async function retryRun(runId: string, body: RunMutation) {
  return (
    await retryTrainingRun({
      baseUrl,
      path: { run_id: runId },
      body,
      throwOnError: true,
    })
  ).data;
}
