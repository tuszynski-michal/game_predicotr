import type {
  AdminApiClient,
  QualityMemberResponse,
  QualityObservation,
  QualityPositionJudgment,
} from '@game-predictor/admin-api-client';

export type GridQualityMeasurementClient = Pick<
  AdminApiClient,
  | 'listGridQualityMeasurements'
  | 'getGridQualityMeasurement'
  | 'captureGridQualityMeasurement'
  | 'assessGridQualityMeasurement'
  | 'approveOperationalGeometry'
>;

export const measurementUuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function measurementHardSources(text: string): string[] {
  const ids = text.trim() ? text.trim().split(/[\s,;]+/) : [];
  if (
    ids.length > 100 ||
    ids.some((id) => !measurementUuid.test(id)) ||
    new Set(ids).size !== ids.length
  )
    throw new Error('Podaj do 100 różnych UUID zdjęć z wybranej gry.');
  return ids;
}

export function measurementJudgments(
  member: QualityMemberResponse,
): QualityPositionJudgment[] {
  return Array.from(
    { length: 9 },
    (_, positionIndex): QualityPositionJudgment => ({
      positionIndex,
      geometry: 'unreviewed',
      detection: 'unreviewed',
      sequence: 'unreviewed',
      ...member.judgments.find((item) => item.positionIndex === positionIndex),
    }),
  );
}

/** A lattice is drawn exactly as stored, without interpolation or moving gaps. */
export function measurementMesh(observation: QualityObservation): string[] {
  const nodes = observation.available ? observation.nodes : null;
  if (
    !nodes?.length ||
    nodes.some(
      (row) =>
        !row.length ||
        row.length !== nodes[0].length ||
        row.some(
          (point) => !Number.isFinite(point.x) || !Number.isFinite(point.y),
        ),
    )
  )
    return [];
  return [
    ...nodes.map((row) => row.map(({ x, y }) => `${x},${y}`).join(' ')),
    ...nodes[0].map((_, column) =>
      nodes.map((row) => `${row[column].x},${row[column].y}`).join(' '),
    ),
  ];
}

export function measurementReviewerUrl(adminOrigin: string): string | null {
  const url = new URL(adminOrigin);
  if (
    !['localhost', '127.0.0.1', '[::1]'].includes(url.hostname) ||
    !['http:', 'https:'].includes(url.protocol)
  )
    return null;
  url.port = '3001';
  url.pathname = '/';
  url.search = '';
  url.hash = '';
  return url.toString();
}
