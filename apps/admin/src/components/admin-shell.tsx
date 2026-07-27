import type { ReactNode } from 'react';

interface AdminShellProps {
  readonly apiBaseUrl: string;
  readonly children: ReactNode;
}

export function AdminShell({ apiBaseUrl, children }: AdminShellProps) {
  return (
    <main className="adminShell">
      <aside className="sidebar" aria-label="Nawigacja panelu">
        <div className="brand">
          <span className="brandMark" aria-hidden="true">
            GP
          </span>
          <div>
            <strong>Game Predictor</strong>
            <span>Local Admin</span>
          </div>
        </div>

        <nav aria-label="Sekcje konfiguracji">
          <a
            aria-current="page"
            className="navItem navItemActive"
            href="#games"
          >
            <span aria-hidden="true">01</span>
            Gry
          </a>
          <a className="navItem navItemAvailable" href="#symbols">
            <span aria-hidden="true">02</span>
            Symbole
          </a>
          <a className="navItem navItemAvailable" href="#rules">
            <span aria-hidden="true">03</span>
            Wersje reguł
          </a>
          <a className="navItem navItemAvailable" href="#datasets">
            <span aria-hidden="true">04</span>
            Datasety
          </a>
          <a className="navItem navItemAvailable" href="#jobs">
            <span aria-hidden="true">05</span>
            Jobs
          </a>
          <a className="navItem navItemAvailable" href="#releases">
            <span aria-hidden="true">06</span>
            Wydania Android
          </a>
        </nav>

        <div className="sidebarFooter">
          <p className="localOnly">Działa wyłącznie lokalnie</p>
          <code title={apiBaseUrl}>{apiBaseUrl}</code>
        </div>
      </aside>

      <section className="content">{children}</section>
    </main>
  );
}
