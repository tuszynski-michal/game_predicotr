'use client';

/* eslint-disable @next/next/no-img-element -- registered local assets; no image optimizer proxy */
import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useToast } from '../../../../packages/ui/src/toasts';
import { useAnnotations } from '../components/annotation-context';
import {
  matchesPhotoFilter,
  photoCounts,
  photoReviewStatus,
  photoReviewLabel,
  sourceAnnotations,
  type PhotoFilter,
} from '../lib/annotation-status';
import { GeometryEditor } from '../components/geometry-editor';
import { FamilyEditor } from '../components/family-editor';
import { QuickReview } from '../components/quick-review';
import { gameDisplayName } from '../lib/game-display-name';
import {
  detectGeometry,
  listSources,
  listRuns,
  type RunState,
  assetUrl,
  type GeometryResult,
  type Source,
} from '../../../../packages/vision-lab-api-client/src/index';

export default function Page() {
  const [catalog, setCatalog] = useState<Source[]>([]);
  const [quick, setQuick] = useState(false);
  const [models, setModels] = useState<RunState[]>([]);
  const [modelRun, setModelRun] = useState('');
  const { state, refresh } = useAnnotations();
  const notify = useToast();
  const [filter, setFilter] = useState<PhotoFilter>('all');
  const [reload, setReload] = useState(0);
  const [protection, setProtection] = useState({
    dirty: false,
    pending: false,
  });
  const onProtectionChange = useCallback(
    (dirty: boolean, pending: boolean) => setProtection({ dirty, pending }),
    [],
  );
  const [games, setGames] = useState<Record<string, string>>({});
  const [game, setGame] = useState('');
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState<Source | null>(null);
  const [result, setResult] = useState<GeometryResult | null>(null);
  const [columns, setColumns] = useState<3 | 5>(5);
  const detectionOrder = useRef(0);
  const onColumnsChange = useCallback((next: 3 | 5) => {
    detectionOrder.current++;
    setColumns(next);
    setResult(null);
  }, []);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [galleryFailed, setGalleryFailed] = useState(false);
  const [familySources, setFamilySources] = useState<Source[]>([]);
  async function refreshModels() {
    try {
      const all: RunState[] = [];
      let page = await listRuns(0, 100);
      all.push(...page.runs);
      while (all.length < page.total) {
        page = await listRuns(all.length, 100);
        if (!page.runs.length) throw new Error('Incomplete run catalog');
        all.push(...page.runs);
      }
      setModels(
        all.filter(
          (run) =>
            run.status === 'succeeded' &&
            run.request.model_version === 'hybrid-mobilenet-v1',
        ),
      );
    } catch {
      notify({
        kind: 'error',
        message: 'Nie można odczytać modeli. Sprawdź konfigurację runów API.',
      });
    }
  }
  const filtered = catalog.filter(
    (source) =>
      (!game || source.game_id === game) &&
      matchesPhotoFilter(
        sourceAnnotations(state, source.id),
        filter,
        state?.photo_reviews?.[source.id],
        source.sha256,
      ),
  );
  const total = filtered.length;
  const pageOffset = Math.min(
    offset,
    Math.max(0, Math.ceil(total / 24) - 1) * 24,
  );
  const sources = filtered.slice(pageOffset, pageOffset + 24);
  useEffect(() => {
    let cancelled = false;
    async function readCatalog() {
      notify({
        kind: 'info',
        message: 'Wczytywanie katalogu zdjęć…',
        operation: 'catalog',
      });
      const all: Source[] = [];
      let data = await listSources();
      const games = data.games;
      all.push(...data.sources);
      while (all.length < data.total && !cancelled) {
        data = await listSources(all.length);
        if (!data.sources.length) throw new Error('Incomplete source catalog');
        all.push(...data.sources);
      }
      return { sources: all, games };
    }
    readCatalog()
      .then((data) => {
        if (!cancelled) {
          setCatalog(data.sources);
          setGames(data.games);
          setLoading(false);
          notify({
            kind: 'success',
            message: `Wczytano ${data.sources.length} zdjęć.`,
            operation: 'catalog',
          });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setGalleryFailed(true);
          notify({
            kind: 'error',
            message:
              'Nie można wczytać galerii. Sprawdź lokalne API i snapshot.',
            operation: 'catalog',
          });
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reload, notify]);
  function canNavigate() {
    if (protection.pending) {
      notify({
        kind: 'warning',
        message:
          'Najpierw rozstrzygnij niepotwierdzony zapis lub zakończ odczyt.',
      });
      return false;
    }
    return true;
  }
  function resetSelection() {
    setSelected(null);
    setResult(null);
    setProtection({ dirty: false, pending: false });
  }
  function changePage(next: number) {
    if (!canNavigate()) return;
    resetSelection();
    setOffset(next);
  }
  function choose(source: Source) {
    if (selected?.id === source.id || !canNavigate()) return;
    setSelected(source);
    setResult(null);
    setProtection({ dirty: false, pending: false });
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
    const order = ++detectionOrder.current;
    try {
      const next = await detectGeometry(
        selected.id,
        columns,
        modelRun || undefined,
      );
      if (order !== detectionOrder.current) return;
      setResult(next);
      if (next.status !== 'detected')
        notify({
          kind: 'warning',
          message: `${modelRun ? 'Hybryda' : 'Baseline'}: ${next.status}. ${next.reasons.join(', ')}`,
        });
    } catch {
      if (order !== detectionOrder.current) return;
      notify({
        kind: 'error',
        message:
          'Analiza nie powiodła się. Możesz ponowić lub wybrać inne zdjęcie.',
      });
    } finally {
      setBusy(false);
    }
  }
  if (quick && state)
    return (
      <QuickReview
        sources={catalog}
        initialState={state}
        game={game}
        onReturn={() => setQuick(false)}
      />
    );
  return (
    <main>
      <header>
        <p className="eyebrow">WIZJA / ANOTACJE</p>
        <h1>Laboratorium geometrii</h1>
        {!protection.pending && !busy && (
          <Link href="/symbols">Etykiety symboli</Link>
        )}
        <button
          disabled={!state || loading || busy || protection.pending}
          onClick={() => {
            if (canNavigate()) {
              resetSelection();
              setQuick(true);
              window.scrollTo?.(0, 0);
            }
          }}
        >
          Szybki przegląd
        </button>
        <p>
          Zdjęcia, propozycje siatek i cropy. Wynik silnika wymaga oceny
          człowieka.
        </p>
      </header>
      <p>
        Liczniki opisują zapisane anotacje, nie kwalifikację treningową. Rola
        katalogowa 777 pozostaje porównawcza; wybrane zatwierdzone geometrie
        uczestniczą w zamrożonym pilocie D-453/D-456. Pilot całymi grami nie
        potwierdza niezależności rodzin nagrań.
      </p>
      <label>
        Gra{' '}
        <select
          value={game}
          disabled={busy}
          onChange={(event) => {
            if (!canNavigate()) return;
            setGame(event.target.value);
            setOffset(0);
            resetSelection();
          }}
        >
          <option value="">Wszystkie gry</option>
          {Object.entries(games).map(([id, name]) => (
            <option key={id} value={id}>
              {gameDisplayName(id, name)}
            </option>
          ))}
        </select>
      </label>
      <label>
        Stan zdjęcia{' '}
        <select
          value={filter}
          disabled={!state || busy}
          onChange={(event) => {
            if (!canNavigate()) return;
            setFilter(event.target.value as PhotoFilter);
            setOffset(0);
            resetSelection();
          }}
        >
          <option value="all">Wszystkie</option>
          <option value="missing">Bez zapisów</option>
          <option value="started">Rozpoczęte (dowolny zapis)</option>
          <option value="full">Z pełną siatką (co najmniej jedną)</option>
          <option value="review">Do przeglądu</option>
          <option value="correction">Do poprawy</option>
          <option value="accepted">Zaakceptowane</option>
        </select>
      </label>
      <div className="action-group">
        <button
          disabled={busy || protection.pending}
          onClick={() => {
            void refresh()
              .then(() =>
                notify({
                  kind: 'info',
                  message: 'Odświeżono statusy zapisanych anotacji.',
                }),
              )
              .catch(() =>
                notify({
                  kind: 'error',
                  message: 'Odczyt anotacji nie powiódł się.',
                }),
              );
          }}
        >
          Odśwież statusy
        </button>
        {galleryFailed && (
          <button
            onClick={() => {
              setLoading(true);
              setGalleryFailed(false);
              setReload((value) => value + 1);
            }}
          >
            Ponów wczytanie galerii
          </button>
        )}
      </div>
      {loading ? (
        <div aria-busy="true" aria-label="Galeria" />
      ) : total === 0 ? (
        <p>Brak zdjęć w tym widoku.</p>
      ) : (
        <>
          <nav>
            <strong>{total} zdjęć</strong>
            <button
              disabled={pageOffset === 0 || busy}
              onClick={() => changePage(Math.max(0, pageOffset - 24))}
            >
              Poprzednie
            </button>
            <span>
              {pageOffset + 1}–{Math.min(total, pageOffset + 24)}
            </span>
            <button
              disabled={pageOffset + 24 >= total || busy}
              onClick={() => changePage(pageOffset + 24)}
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
                    notify({
                      kind: 'error',
                      message: `Nie można odczytać zdjęcia: ${source.filename}`,
                    });
                  }}
                />
                <strong>
                  {gameDisplayName(source.game_id, source.game_name)}
                </strong>
                <small>{source.filename}</small>
                {state ? (
                  <small className="annotation-badge">
                    Pełne:{' '}
                    {photoCounts(sourceAnnotations(state, source.id)).full} ·
                    Lokalizacje:{' '}
                    {photoCounts(sourceAnnotations(state, source.id)).location}{' '}
                    · Szkice:{' '}
                    {photoCounts(sourceAnnotations(state, source.id)).draft}
                    <br />
                    {
                      photoReviewLabel[
                        photoReviewStatus(
                          sourceAnnotations(state, source.id),
                          state.photo_reviews?.[source.id],
                          source.sha256,
                        ).status
                      ]
                    }{' '}
                    · Do poprawy:{' '}
                    {
                      photoReviewStatus(
                        sourceAnnotations(state, source.id),
                        state.photo_reviews?.[source.id],
                        source.sha256,
                      ).correction
                    }{' '}
                    · Ponowny przegląd:{' '}
                    {
                      photoReviewStatus(
                        sourceAnnotations(state, source.id),
                        state.photo_reviews?.[source.id],
                        source.sha256,
                      ).recheck
                    }
                  </small>
                ) : (
                  <small>Stan anotacji niedostępny</small>
                )}
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
          <h2>
            {gameDisplayName(selected.game_id, selected.game_name)} — podgląd
          </h2>
          <p>{selected.filename}</p>
          <GeometryEditor
            key={selected.id}
            source={selected}
            proposal={result}
            columns={columns}
            onProtectionChange={onProtectionChange}
            onColumnsChange={onColumnsChange}
          />
          <p>
            Kandydat rodziny: {selected.family_candidate} ·{' '}
            {selected.role === 'comparison_only'
              ? 'Rola katalogowa: porównawcza; kwalifikacja geometrii jest osobna'
              : 'Rola katalogowa: materiał testowy'}
          </p>
          <button disabled={busy} onClick={detect}>
            {busy
              ? 'Analiza zdjęcia…'
              : modelRun
                ? 'Pokaż wynik hybrydy'
                : 'Pokaż wynik baseline'}
          </button>
          <label>
            Model podglądu
            <select
              aria-label="Model podglądu"
              value={modelRun}
              disabled={busy || protection.pending}
              onChange={(event) => {
                detectionOrder.current++;
                setResult(null);
                setModelRun(event.target.value);
              }}
            >
              <option value="">Baseline (domyślny)</option>
              {models.map((run) => (
                <option key={run.id} value={run.id}>
                  Hybryda {run.id.slice(0, 8)} · epoka {run.best_epoch} · wymaga
                  przeglądu
                </option>
              ))}
            </select>
          </label>
          <button disabled={busy} onClick={refreshModels}>
            Odśwież dostępne modele
          </button>
          {modelRun && (
            <p>
              Eksperymentalna hybryda, bramka niekalibrowana. Każda propozycja
              wymaga przeglądu. Tylko development/validation.
            </p>
          )}
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
              <p>
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
