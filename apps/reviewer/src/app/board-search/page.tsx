import '@game-predictor/board-search-ui/board-search.css';

import { notFound } from 'next/navigation';

import { BoardSearchShareGate } from '@/features/board-search-share/board-search-share-gate';
import { isBoardSearchShareEnabled } from '@/security/board-search-share-proxy';

const SESSION_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export default async function BoardSearchSharePage({
  searchParams,
}: {
  readonly searchParams: Promise<{
    readonly share?: string | readonly string[];
  }>;
}) {
  if (!isBoardSearchShareEnabled()) notFound();
  const params = await searchParams;
  const raw = params.share;
  const candidate = typeof raw === 'string' ? raw : (raw?.[0] ?? '');
  return (
    <BoardSearchShareGate
      sessionId={SESSION_ID.test(candidate) ? candidate : ''}
    />
  );
}
