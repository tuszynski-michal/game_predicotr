import { AdminShell } from '@/components/admin-shell';
import { GameCatalog } from '@/features/games/game-catalog';
import { resolveAdminApiBaseUrl } from '@/config/admin-api';

export default function HomePage() {
  const apiBaseUrl = resolveAdminApiBaseUrl(
    process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL,
  );

  return (
    <AdminShell apiBaseUrl={apiBaseUrl}>
      <GameCatalog apiBaseUrl={apiBaseUrl} />
    </AdminShell>
  );
}
