import {
  detectGeometry as detect,
  listSources as list,
} from './generated/sdk.gen';
export type { GeometryResult, Source } from './generated/types.gen';

const baseUrl = '/api/lab';
export async function listSources(offset = 0, game?: string) {
  const response = await list({
    baseUrl,
    query: { offset, limit: 24, game },
    throwOnError: true,
  });
  return response.data;
}
export async function detectGeometry(sourceId: string, columns: 3 | 5) {
  const response = await detect({
    baseUrl,
    body: { source_id: sourceId, topology: { columns, rows: 3 } },
    throwOnError: true,
  });
  return response.data;
}
export function assetUrl(assetId: string) {
  return `${baseUrl}/assets/${encodeURIComponent(assetId)}`;
}
