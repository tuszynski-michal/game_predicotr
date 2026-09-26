'use client';

/* eslint-disable @next/next/no-img-element -- registered local assets; no image optimizer proxy */
import { useEffect, useState } from 'react';
import { GeometryEditor } from '../components/geometry-editor';
import { FamilyEditor } from '../components/family-editor';
import {
  detectGeometry,
  listSources,
  assetUrl,
  type GeometryResult,
  type Source,
} from '../../../../packages/vision-lab-api-client/src/index';

export default function Page() {
  const [sources, setSources] = useState<Source[]>([]);
  const [total, setTotal] = useState(0);
  const [games, setGames] = useState<Record<string, string>>({});
  const [game, setGame] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Source | null>(null);
  const [result, setResult] = useState<GeometryResult | null>(null);
  const [columns, setColumns] = useState<3 | 5>(5);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [familySources, setFamilySources] = useState<Source[]>([]);
  useEffect(() => {
    let cancelled = false;
    listSources(offset, game || undefined)
      .then((data) => {
        if (!cancelled) {
          setSources(data.sources);
          setTotal(data.total);
          setGames(data.games);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(
            'Nie można wczytać galerii. Sprawdź lokalne API i snapshot.',
          );
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [offset, game]);
  function changePage(next: number) {
    setLoading(true);
    setOffset(next);
  }
  function choose(source: Source) {
    setSelected(source);
    setResult(null);
    setError('');
    setTimeout(
      () =>
        document
          .getElementById('inspector')
          ?.scrollIntoView({ behavior: 'smooth' }),
      0,
    );
  }
  async function detect() {
    if (!selected || busy) return;
    setBusy(true);
    setResult(null);
    setError('');
    try {
      setResult(await detectGeometry(selected.id, columns));
    } catch {
      setError(
        'Analiza nie powiodła się. Możesz ponowić lub wybrać inne zdjęcie.',
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main>
      <header>
        <p className="eyebrow">WIZJA / ANOTACJE</p>
        <h1>Laboratorium geometrii</h1>
        <p>
          Zdjęcia, propozycje siatek i cropy. Wynik silnika wymaga oceny
          człowieka.
        </p>
      </header>
      <aside className="notice">
        Materiał wyłącznie do podglądu i testowania. Brak zatwierdzonych etykiet
        i kwalifikacji treningowej. 777: tylko porównanie. Rodziny nagrań
        wymagają weryfikacji.
      </aside>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <label>
        Gra{' '}
        <select
          value={game}
          disabled={busy}
          onChange={(event) => {
            setLoading(true);
            setGame(event.target.value);
            setOffset(0);
            setSelected(null);
            setResult(null);
          }}
        >
          <option value="">Wszystkie gry</option>
          {Object.entries(games).map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>
      </label>
      {loading ? (
        <p role="status">Wczytywanie zdjęć…</p>
      ) : total === 0 ? (
        <p>
          Brak zdjęć. Uruchom API ze zmienną VISION_LAB_SNAPSHOT wskazującą
          opublikowany snapshot.
        </p>
      ) : (
        <>
          <nav>
            <strong>{total} zdjęć</strong>
            <button
              disabled={offset === 0 || busy}
              onClick={() => changePage(Math.max(0, offset - 24))}
            >
              Poprzednie
            </button>
            <span>
              {offset + 1}–{Math.min(total, offset + 24)}
            </span>
            <button
              disabled={offset + 24 >= total || busy}
              onClick={() => changePage(offset + 24)}
            >
              Następne
            </button>
          </nav>
          <section className="gallery" aria-label="Zdjęcia źródłowe">
            {sources.map((source) => (
              <button
                className={
                  selected?.id === source.id ? 'card selected' : 'card'
                }
                key={source.id}
                disabled={busy}
                onClick={() => choose(source)}
              >
                <img
                  loading="lazy"
                  src={assetUrl(source.asset_id)}
                  alt={source.filename}
                  onError={(event) => {
                    event.currentTarget.alt = 'Nie można odczytać zdjęcia';
                  }}
                />
                <strong>{source.game_name}</strong>
                <small>{source.filename}</small>
                {source.duplicate_count > 1 && (
                  <small>Duplikat: {source.duplicate_count} wystąpienia</small>
                )}
              </button>
            ))}
          </section>
        </>
      )}
      <FamilyEditor
        sources={sources}
        selected={familySources}
        onSelected={setFamilySources}
      />
      {selected && (
        <section id="inspector" className="inspector">
          <h2>{selected.game_name} — podgląd</h2>
          <p>{selected.filename}</p>
          <GeometryEditor
            key={`${selected.id}:${columns}`}
            source={selected}
            proposal={result}
            columns={columns}
          />
          <p>
            Kandydat rodziny: {selected.family_candidate} ·{' '}
            {selected.role === 'comparison_only'
              ? 'Tylko porównanie'
              : 'Materiał testowy'}
          </p>
          <label>
            Topologia planszy{' '}
            <select
              value={columns}
              disabled={busy}
              onChange={(event) => {
                setColumns(Number(event.target.value) as 3 | 5);
                setResult(null);
              }}
            >
              <option value={5}>5 kolumn × 3 wiersze</option>
              <option value={3}>3 kolumny × 3 wiersze</option>
            </select>
          </label>
          <button disabled={busy} onClick={detect}>
            {busy ? 'Analiza zdjęcia…' : 'Pokaż wynik baseline'}
          </button>
          <div className="photo">
            <img src={assetUrl(selected.asset_id)} alt="Wybrane zdjęcie" />
            {result && result.width > 0 && (
              <svg
                viewBox={`0 0 ${result.width} ${result.height}`}
                aria-label="Propozycja siatki"
              >
                <title>Propozycja siatki, niezatwierdzona</title>
                {result.boards.map((board) => (
                  <g key={board.position_index}>
                    {board.nodes.map((point, index) => (
                      <circle
                        key={index}
                        cx={point.x}
                        cy={point.y}
                        r={Math.max(3, result.width / 350)}
                        fill={
                          board.status === 'complete' ? '#5dffab' : '#ffce54'
                        }
                      />
                    ))}
                    {Array.from(
                      { length: result.topology.rows + 1 },
                      (_, row) => (
                        <polyline
                          key={`r${row}`}
                          points={board.nodes
                            .slice(
                              row * (columns + 1),
                              (row + 1) * (columns + 1),
                            )
                            .map((p) => `${p.x},${p.y}`)
                            .join(' ')}
                          fill="none"
                          stroke="#5dffab"
                          strokeWidth={result.width / 700}
                        />
                      ),
                    )}
                    {Array.from({ length: columns + 1 }, (_, column) => (
                      <polyline
                        key={`c${column}`}
                        points={board.nodes
                          .filter((_, i) => i % (columns + 1) === column)
                          .map((p) => `${p.x},${p.y}`)
                          .join(' ')}
                        fill="none"
                        stroke="#5dffab"
                        strokeWidth={result.width / 700}
                      />
                    ))}
                  </g>
                ))}
              </svg>
            )}
          </div>
          {result && (
            <>
              <p role="status">
                {result.status} · {result.model_version}{' '}
                {result.reasons.join(', ')}
              </p>
              {result.status === 'unsupported' && (
                <p>
                  Baseline nie obsługuje topologii 3 × 3. Kontrakt galerii
                  obsługuje 16 węzłów.
                </p>
              )}
              {result.boards.map((board) => (
                <section key={board.position_index}>
                  <h3>
                    Plansza {board.position_index + 1}: {board.status}
                  </h3>
                  <p>
                    {board.reasons.join(', ') ||
                      'Propozycja — bez zatwierdzenia'}
                  </p>
                  <div className="crops">
                    {board.cells.map((cell) => (
                      <figure key={cell.index}>
                        {cell.asset_id ? (
                          <img
                            src={assetUrl(cell.asset_id)}
                            alt={`Komórka ${cell.index + 1}`}
                          />
                        ) : (
                          <div>Poza zdjęciem</div>
                        )}
                        <figcaption>
                          {cell.index + 1} · {cell.status}
                        </figcaption>
                      </figure>
                    ))}
                  </div>
                </section>
              ))}
            </>
          )}
        </section>
      )}
    </main>
  );
}
