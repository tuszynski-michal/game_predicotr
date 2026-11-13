import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import { SymbolOutlineReview } from '@/features/model-quality/symbol-outline-review';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** D-608: separate window opened from „Geometria V3” for one game. */
export default async function SymbolOutlinesPage({
  searchParams,
}: {
  readonly searchParams: Promise<{ gameId?: string | string[] }>;
}) {
  const { gameId } = await searchParams;
  const apiBaseUrl = resolveAdminApiBaseUrl(
    process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL,
  );
  if (typeof gameId !== 'string' || !UUID.test(gameId))
    return (
      <main className="symbolOutlineReview">
        <p role="alert">Otwórz to okno z sekcji „Geometria V3” wybranej gry.</p>
      </main>
    );
  return <SymbolOutlineReview apiBaseUrl={apiBaseUrl} gameId={gameId} />;
}
