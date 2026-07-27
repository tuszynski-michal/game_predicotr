import { AdminShell } from '@/components/admin-shell';
import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import { CatalogWorkspace } from '@/features/catalog/catalog-workspace';

export default function HomePage() {
  const apiBaseUrl = resolveAdminApiBaseUrl(
    process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL,
  );

  return (
    <AdminShell apiBaseUrl={apiBaseUrl}>
      <CatalogWorkspace apiBaseUrl={apiBaseUrl} />
    </AdminShell>
  );
}
