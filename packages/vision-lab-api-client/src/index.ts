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
