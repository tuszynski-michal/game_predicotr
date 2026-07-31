import type { ReactNode } from 'react';

interface AdminShellProps {
  readonly apiBaseUrl: string;
  readonly children: ReactNode;
}

export function AdminShell({ apiBaseUrl, children }: AdminShellProps) {
  return (
    <main className="adminShell">
      <aside className="sidebar" aria-label="Informacje o panelu">
        <div className="brand">
          <span className="brandMark" aria-hidden="true">
            GP
          </span>
          <div>
            <strong>Game Predictor</strong>
            <span>Local Admin</span>
          </div>
        </div>

        <div className="sidebarSummary">
          <p className="eyebrow">Admin 0.2</p>
          <strong>Jeden kontekst pracy</strong>
          <p>Wybierz obszar w górnej części ekranu.</p>
        </div>

        <div className="sidebarFooter">
          <p className="localOnly">Działa wyłącznie lokalnie</p>
          <code title={apiBaseUrl}>{apiBaseUrl}</code>
        </div>
      </aside>

      <section className="content">{children}</section>
    </main>
  );
}
