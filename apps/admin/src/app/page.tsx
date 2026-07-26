import { resolveAdminApiBaseUrl } from '@/config/admin-api';

const foundationItems = [
  {
    label: 'Panel administracyjny',
    value: 'Next.js App Router',
    state: 'gotowy',
  },
  {
    label: 'Lokalne Admin API',
    value: 'FastAPI /api/v1',
    state: 'gotowy',
  },
  {
    label: 'Baza danych',
    value: 'PostgreSQL + Alembic',
    state: 'następny etap',
  },
] as const;

export default function HomePage() {
  const apiBaseUrl = resolveAdminApiBaseUrl(
    process.env.NEXT_PUBLIC_ADMIN_API_BASE_URL,
  );

  return (
    <main className="shell">
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

        <nav aria-label="Sekcje">
          <a className="navItem navItemActive" href="#foundation">
            Fundament
          </a>
          <span className="navItem navItemDisabled">Gry i symbole</span>
          <span className="navItem navItemDisabled">Reguły wypłat</span>
          <span className="navItem navItemDisabled">Datasety</span>
        </nav>

        <p className="localOnly">Działa wyłącznie lokalnie</p>
      </aside>

      <section className="content" id="foundation">
        <header className="pageHeader">
          <div>
            <p className="eyebrow">M2 · Konfiguracja administracyjna</p>
            <h1>Fundament panelu jest gotowy</h1>
            <p className="lead">
              Aplikacje webowa i API mają stabilną lokalną konfigurację. Funkcje
              zarządzania danymi pojawią się w kolejnych zadaniach M2.
            </p>
          </div>
          <span className="statusBadge">
            <span aria-hidden="true" />
            Local
          </span>
        </header>

        <div className="foundationGrid">
          {foundationItems.map((item) => (
            <article className="foundationCard" key={item.label}>
              <span className="cardState">{item.state}</span>
              <h2>{item.label}</h2>
              <p>{item.value}</p>
            </article>
          ))}
        </div>

        <section className="connectionCard" aria-labelledby="connection-title">
          <div>
            <p className="eyebrow">Konfiguracja połączenia</p>
            <h2 id="connection-title">Lokalny adres Admin API</h2>
          </div>
          <code>{apiBaseUrl}</code>
          <p>
            Panel akceptuje wyłącznie adres loopback. Nie publikuje API w sieci
            lokalnej ani w Internecie.
          </p>
        </section>

        <section className="notice" aria-labelledby="scope-title">
          <div className="noticeIcon" aria-hidden="true">
            01
          </div>
          <div>
            <h2 id="scope-title">Świadomie ograniczony zakres</h2>
            <p>
              Ten ekran potwierdza działanie fundamentu. Nie zapisuje jeszcze
              gier, symboli, reguł ani layoutów i nie udaje gotowego CRUD.
            </p>
          </div>
        </section>
      </section>
    </main>
  );
}
