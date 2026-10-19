import '@game-predictor/board-search-ui/board-search.css';
import '@game-predictor/board-search-ui/super-game-series.css';
import { notFound } from 'next/navigation';
import { BoardSearchPanelGate } from '@/features/board-search-panel/board-search-panel-gate';
import { isBoardSearchShareEnabled } from '@/security/board-search-share-proxy';

export default async function BoardSearchPanelPage({
  searchParams,
}: {
  readonly searchParams: Promise<{
    readonly share?: string | readonly string[];
  }>;
}) {
  if (!isBoardSearchShareEnabled()) notFound();
  const raw = (await searchParams).share;
  const panelId =
    typeof raw === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      raw,
    )
      ? raw.toLowerCase()
      : '';
  return <BoardSearchPanelGate key={panelId} panelId={panelId} />;
}
