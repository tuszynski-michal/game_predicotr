import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { headers } from 'next/headers';
import { notFound } from 'next/navigation';

import {
  isLoopbackReviewerHost,
  resolveLocalAdminApiBaseUrl,
} from '@/config/admin-api';
import { ReviewerAccessGate } from '@/features/access/reviewer-access-gate';

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default async function PhotoSeriesPage({
  params,
}: {
  readonly params: Promise<{ name: string; index: string }>;
}) {
  const { name, index } = await params;
  if (
    !isLoopbackReviewerHost((await headers()).get('host')) ||
    !/^[a-z0-9][a-z0-9-]{0,63}$/.test(name) ||
    !/^[1-9][0-9]{0,4}$/.test(index)
  )
    notFound();

  // npm runs this workspace with apps/reviewer as its working directory.
  const root = path.resolve(
    process.cwd(),
    '../..',
    process.env.GAME_PREDICTOR_ARTIFACT_ROOT || 'artifacts',
  );
  const filename = path.join(root, 'reviewer-photo-series', name + '.json');
  let contents: string;
  try {
    contents = await readFile(filename, 'utf8');
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') notFound();
    throw error;
  }
  const series = JSON.parse(contents);
  const position = Number(index);
  if (
    !series ||
    typeof series.gameId !== 'string' ||
    !UUID.test(series.gameId) ||
    !Array.isArray(series.photos) ||
    position > series.photos.length
  )
    notFound();
  const item = series.photos[position - 1];
  if (
    !item ||
    typeof item.importJobId !== 'string' ||
    !UUID.test(item.importJobId) ||
    typeof item.sourceImageId !== 'string' ||
    !UUID.test(item.sourceImageId)
  )
    notFound();
  return (
    <ReviewerAccessGate
      apiBaseUrl={resolveLocalAdminApiBaseUrl(
        process.env.REVIEWER_INTERNAL_API_ORIGIN,
      )}
      localScope={{
        gameId: series.gameId,
        importJobId: item.importJobId,
        sourceImageId: item.sourceImageId,
      }}
      photoSeries={{
        position,
        total: series.photos.length,
        nextHref:
          position < series.photos.length
            ? `/geometria-zdjecia/seria/${name}/${position + 1}`
            : null,
      }}
      sessionId=""
    />
  );
}
