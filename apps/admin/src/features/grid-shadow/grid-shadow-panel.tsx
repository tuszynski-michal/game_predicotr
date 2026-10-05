'use client';

import type {
  AdminApiClient,
  GridShadowResultResponse,
  GridShadowResultPageResponse,
  ImageGridReviewItemResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';

import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { startLocalReviewerProcess } from '@/features/reviewer-access/reviewer-local-start';

import {
  gridShadowMeshLines,
  gridShadowRequestId,
  gridShadowReviewerUrl,
  gridShadowSourceChoices,
  gridShadowStateLabel,
  gridShadowReasonLabels,
  gridShadowErrorMessage,
  gridShadowUnknownVisibilityCount,
} from './grid-shadow-state';
import styles from './grid-shadow.module.css';

export type GridShadowPanelClient = Pick<
  AdminApiClient,
  | 'listImageGridReviews'
  | 'startGridShadowJob'
  | 'listGridShadowResults'
  | 'getGridShadowResult'
  | 'imageGridReviewSourceAssetUrl'
  | 'startLocalReviewer'
  | 'getJob'
>;

export function GridShadowPanel({
  api,
  gameId,
}: {
  readonly api: GridShadowPanelClient;
  readonly gameId: string;
}) {
  const [sources, setSources] = useState<
    readonly ImageGridReviewItemResponse[]
  >([]);
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [page, setPage] = useState<GridShadowResultPageResponse | null>(null);
  const [detail, setDetail] = useState<GridShadowResultResponse | null>(null);
  const [job, setJob] = useState<JobResponse | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [sourcesState, setSourcesState] = useState<
    'loading' | 'ready' | 'error'
  >('loading');
  const [historyState, setHistoryState] = useState<
    'loading' | 'ready' | 'error'
  >('loading');
  const [detailLoading, setDetailLoading] = useState(false);
  const mounted = useRef(false);
  const generation = useRef(0);
  const detailRequest = useRef(0);
  const actionPending = useRef(false);
  const invalidatePendingRequests = useCallback(() => {
    mounted.current = false;
    generation.current++;
    detailRequest.current++;
  }, []);

  const load = useCallback(
    async (cursor?: string) => {
      const current = ++generation.current;
      setBusy(true);
      setError('');
      setSourcesState('loading');
      setHistoryState('loading');
      detailRequest.current++;
      setDetailLoading(false);
      try {
        const [reviews, results] = await Promise.all([
          api.listImageGridReviews({ gameId, view: 'all', limit: 100 }),
          api.listGridShadowResults({
            gameId,
            limit: 20,
            ...(cursor ? { cursor } : {}),
          }),
        ]);
        if (!mounted.current || current !== generation.current) return;
        if (reviews.data && reviews.error === undefined) {
          setSources(gridShadowSourceChoices(reviews.data.items));
          setSourcesState('ready');
        } else setSourcesState('error');
        if (results.data && results.error === undefined) {
          setPage(results.data);
          setHistoryState('ready');
        } else setHistoryState('error');
        if (reviews.error !== undefined || results.error !== undefined)
          setError(
            apiErrorMessage(
              reviews.error ?? results.error,
              'Nie udało się odczytać porównania siatek.',
            ),
          );
      } catch {
        if (mounted.current && current === generation.current) {
          setError('Połączenie z lokalnym Admin API zostało przerwane.');
          setSourcesState('error');
          setHistoryState('error');
        }
      } finally {
        if (mounted.current && current === generation.current) setBusy(false);
      }
    },
    [api, gameId],
  );

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => {
      setSelected([]);
      setDetail(null);
      setJob(null);
      setPage(null);
      void load();
    });
    return invalidatePendingRequests;
  }, [load, invalidatePendingRequests]);

  async function readResult(id: string) {
    const current = ++detailRequest.current;
    const scope = generation.current;
    setDetail(null);
    setDetailLoading(true);
    setError('');
    try {
      const result = await api.getGridShadowResult(gameId, id);
      if (
        !mounted.current ||
        current !== detailRequest.current ||
        scope !== generation.current
      )
        return;
      if (result.error !== undefined || !result.data)
        setError(
          apiErrorMessage(result.error, 'Nie udało się odczytać wyniku.'),
        );
      else setDetail(result.data);
    } catch {
      if (
        mounted.current &&
        current === detailRequest.current &&
        scope === generation.current
      )
        setError('Nie udało się odczytać wyniku.');
    } finally {
      if (
        mounted.current &&
        current === detailRequest.current &&
        scope === generation.current
      )
        setDetailLoading(false);
    }
  }

  async function start() {
    if (actionPending.current || selected.length === 0 || selected.length > 20)
      return;
    actionPending.current = true;
    setBusy(true);
    setError('');
    const scope = generation.current;
    try {
      const requestId = gridShadowRequestId(
        window.localStorage,
        gameId,
        selected,
        () => crypto.randomUUID(),
      );
      const response = await api.startGridShadowJob({
        gameId,
        requestId,
        sourceImageIds: [...selected],
      });
      if (!mounted.current || scope !== generation.current) return;
      if (response.error !== undefined || !response.data)
        setError(
          gridShadowErrorMessage(
            response.error,
            'Nie udało się uruchomić porównania. Tryb porównawczy musi być włączony przez operatora.',
          ),
        );
      else setJob(response.data);
    } catch {
      if (mounted.current && scope === generation.current)
        setError(
          'Nie otrzymano odpowiedzi. Ponowienie dla tych samych zdjęć odzyska to samo zadanie.',
        );
    } finally {
      actionPending.current = false;
      if (mounted.current && scope === generation.current) setBusy(false);
    }
  }

  async function refresh() {
    const scope = generation.current;
    try {
      if (job !== null) {
        const response = await api.getJob(job.id);
        if (!mounted.current || scope !== generation.current) return;
        if (response.data && response.error === undefined)
          setJob(response.data);
      }
      if (!mounted.current || scope !== generation.current) return;
      await load();
    } catch {
      if (mounted.current && scope === generation.current)
        setError('Nie udało się odświeżyć zadania.');
    }
  }

  async function startNew() {
    if (
      !job ||
      !['completed', 'failed', 'cancelled'].includes(job.status) ||
      actionPending.current
    )
      return;
    window.localStorage.removeItem(`grid-shadow-request:${gameId}`);
    await start();
  }

  async function openCorrection(
    result: GridShadowResultResponse,
    positionIndex: number,
  ) {
    if (actionPending.current) return;
    const url = gridShadowReviewerUrl(
      window.location.href,
      gameId,
      result.id,
      positionIndex,
    );
    if (url === null) {
      setError('Korektę porównania można otworzyć tylko z lokalnego Admina.');
      return;
    }
    const popup = window.open(url, '_blank');
    if (popup) popup.opener = null;
    actionPending.current = true;
    const scope = generation.current;
    try {
      const started = await startLocalReviewerProcess(api);
      if (!mounted.current || scope !== generation.current) {
        popup?.close();
        return;
      }
      if (!started.ok) {
        popup?.close();
        setError(started.error);
      } else if (popup) popup.location.href = url;
      else
        setError(
          'Przeglądarka zablokowała nowe okno Reviewera. Zezwól na otwieranie okien i ponów.',
        );
    } finally {
      actionPending.current = false;
    }
  }

  return (
    <section className={styles.panel} aria-label="Porównanie siatek sieci">
      <h2>Porównanie siatek sieci</h2>
      <p>
        Wybierz do 20 istniejących zdjęć. Wynik jest propozycją do ręcznej
        korekty. Samo porównanie nie zmienia zapisanych siatek ani symboli.
      </p>
      <fieldset disabled={busy}>
        <legend>
          Zdjęcia z pierwszych 100 pozycji gry · wybrano {selected.length}/20
        </legend>
        {sourcesState === 'loading' ? (
          <p role="status">Wczytywanie listy zdjęć…</p>
        ) : sourcesState === 'error' ? (
          <p>Nie udało się pobrać listy zdjęć. Odśwież wyniki, aby ponowić.</p>
        ) : sources.length === 0 ? (
          <p>
            Brak zmaterializowanych zdjęć. Najpierw zakończ przygotowanie i
            import plansz.
          </p>
        ) : (
          sources.map((item) => (
            <label key={item.sourceImageId} className={styles.choice}>
              <input
                type="checkbox"
                checked={selected.includes(item.sourceImageId)}
                disabled={
                  !selected.includes(item.sourceImageId) &&
                  selected.length >= 20
                }
                onChange={(event) =>
                  setSelected((current) =>
                    event.target.checked
                      ? [...current, item.sourceImageId]
                      : current.filter((id) => id !== item.sourceImageId),
                  )
                }
              />
              Zdjęcie od planszy {item.sequenceNumber}
            </label>
          ))
        )}
      </fieldset>
      <div className={styles.actions}>
        <button
          type="button"
          className="primaryButton"
          disabled={busy || selected.length === 0}
          onClick={() => void start()}
        >
          Porównaj wybrane zdjęcia
        </button>
        <button
          type="button"
          className="secondaryButton"
          disabled={busy}
          onClick={() => void refresh()}
        >
          Odśwież wyniki
        </button>
      </div>
      {job ? <p role="status">{gridShadowStateLabel(job.status)}</p> : null}
      {job && ['completed', 'failed', 'cancelled'].includes(job.status) ? (
        <button
          type="button"
          className="secondaryButton"
          disabled={busy || selected.length === 0}
          onClick={() =>
            void startNew().catch(() =>
              setError('Nie udało się rozpocząć nowego porównania.'),
            )
          }
        >
          Nowe porównanie tych samych zdjęć
        </button>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {historyState === 'loading' ? (
        <p role="status">Wczytywanie historii porównań…</p>
      ) : historyState === 'error' ? (
        <p>Nie udało się pobrać historii porównań.</p>
      ) : page?.items.length === 0 ? (
        <p>
          Nie ma jeszcze wyników porównań. Wybierz zdjęcia i rozpocznij
          porównanie.
        </p>
      ) : (
        <ul>
          {page?.items.map((result) => (
            <li key={result.id}>
              <button
                type="button"
                className="secondaryButton"
                onClick={() => void readResult(result.id)}
              >
                Porównanie z{' '}
                {new Date(result.createdAt).toLocaleString('pl-PL')} ·{' '}
                {result.stale
                  ? 'Nieaktualne'
                  : gridShadowStateLabel(result.status)}
              </button>
            </li>
          ))}
        </ul>
      )}
      {page?.nextCursor ? (
        <button
          type="button"
          className="secondaryButton"
          disabled={busy}
          onClick={() => void load(page.nextCursor ?? undefined)}
        >
          Następne wyniki
        </button>
      ) : null}
      {detailLoading ? (
        <p role="status">Wczytywanie wyniku porównania…</p>
      ) : null}
      {detail ? (
        <GridShadowComparison
          key={`${detail.id}:${detail.sourceChecksumSha256}`}
          api={api}
          result={detail}
          onCorrect={(index) => void openCorrection(detail, index)}
        />
      ) : null}
    </section>
  );
}

function GridShadowComparison({
  api,
  result,
  onCorrect,
}: {
  readonly api: GridShadowPanelClient;
  readonly result: GridShadowResultResponse;
  readonly onCorrect: (index: number) => void;
}) {
  const [imageState, setImageState] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );
  const url = result.sourceAssetReviewItemId
    ? api.imageGridReviewSourceAssetUrl(
        result.sourceAssetReviewItemId,
        result.gameId,
        result.sourceChecksumSha256,
      )
    : null;
  return (
    <section aria-label="Wynik porównania">
      <p>
        Plansze w tym zdjęciu: {result.output.slots.length}. Wszystkie
        propozycje wymagają ręcznego sprawdzenia.
      </p>
      {result.stale ? (
        <p role="alert">
          Wynik nieaktualny. Geometria lub źródło zmieniły się. Korekta tej
          propozycji jest zablokowana.
        </p>
      ) : null}
      <p>
        Linia ciągła: zapisana siatka. Linia przerywana i punkty: pełne 24 węzły
        sieci.
      </p>
      {imageState === 'error' ? (
        <p role="alert">
          Nie udało się wczytać zdjęcia. Nakładka siatek jest ukryta; odśwież
          wynik.
        </p>
      ) : url ? (
        <>
          <p role="status">
            {imageState === 'loading'
              ? 'Wczytywanie zdjęcia…'
              : 'Zdjęcie wczytane'}
          </p>
          <svg
            className={styles.image}
            style={{
              visibility: imageState === 'loading' ? 'hidden' : 'visible',
            }}
            viewBox={`0 0 ${result.sourceWidth} ${result.sourceHeight}`}
            role="img"
            aria-label="Zdjęcie z zapisaną siatką i pełną siatką sieci"
          >
            <image
              href={url}
              width={result.sourceWidth}
              height={result.sourceHeight}
              onLoad={() => setImageState('ready')}
              onError={() => setImageState('error')}
            />
            {result.output.slots.map((slot) => (
              <g key={slot.positionIndex}>
                <title>
                  Plansza {slot.sequenceNumber}: zapisana siatka i propozycja
                  sieci
                </title>
                {gridShadowMeshLines(slot.baselineNodes24 ?? []).map(
                  (line, i) => (
                    <polyline
                      key={`base-${i}`}
                      points={line}
                      fill="none"
                      stroke="#f14b57"
                      strokeWidth="2"
                    />
                  ),
                )}
                {gridShadowMeshLines(slot.neuralNodes24 ?? []).map(
                  (line, i) => (
                    <polyline
                      key={`net-${i}`}
                      points={line}
                      fill="none"
                      stroke="#ffe267"
                      strokeDasharray="7 4"
                      strokeWidth="2"
                    />
                  ),
                )}
                {slot.neuralNodes24?.map((point, i) => (
                  <circle
                    key={i}
                    cx={point.x}
                    cy={point.y}
                    r="2.5"
                    fill="#ffe267"
                  />
                ))}
              </g>
            ))}
          </svg>
        </>
      ) : (
        <p>
          Podgląd źródła niedostępny dla tego wyniku. Metadane pozostają
          widoczne.
        </p>
      )}
      <p>
        {gridShadowReasonLabels([
          ...result.reasons,
          ...result.output.slots.flatMap((slot) => slot.reasonCodes ?? []),
        ])}
      </p>
      <ul>
        {result.output.slots.map((slot) => (
          <li key={slot.positionIndex}>
            Plansza {slot.sequenceNumber} · pozycja {slot.positionIndex + 1} ·{' '}
            {gridShadowStateLabel(slot.state)} · pola poza zdjęciem:{' '}
            {slot.cellVisibility.filter((state) => state === 'outside').length}{' '}
            · częściowe:{' '}
            {slot.cellVisibility.filter((state) => state === 'partial').length}{' '}
            {gridShadowUnknownVisibilityCount(slot.cellVisibility) > 0 ? (
              <>
                {' '}
                · Nieustalona widoczność:{' '}
                {gridShadowUnknownVisibilityCount(slot.cellVisibility)}{' '}
              </>
            ) : null}
            <button
              type="button"
              className="secondaryButton"
              disabled={result.stale || slot.reviewItem == null}
              onClick={() => onCorrect(slot.positionIndex)}
            >
              Otwórz korektę
            </button>
          </li>
        ))}
      </ul>
      <p>
        Nieprzypisane wykrycia:{' '}
        {result.output.unassignedDetections?.length ?? 0}. Nie tworzą
        dodatkowych aktywnych plansz.
      </p>
      <details>
        <summary>Szczegóły techniczne porównania</summary>
        <p>
          Model sieci: {result.modelProfile} · {result.modelVersion}. Rewizja
          źródła: {result.sourceGeometryRevision}. SHA:{' '}
          <code>{result.sourceChecksumSha256}</code>.
        </p>
        <p>
          Wynik: {result.id} · zadanie: {result.jobId}
        </p>
        <p>
          Powody:{' '}
          {[
            ...result.reasons,
            ...result.output.slots.flatMap((slot) => slot.reasonCodes ?? []),
          ].join(', ') || '—'}
        </p>
        <p>
          Zamrożona geometria źródła:{' '}
          {result.baselineEngineName ?? 'Nie zapisano nazwy silnika'} ·{' '}
          {result.baselineEngineVersion ?? 'Nie zapisano wersji'}. Pochodzenie:{' '}
          {result.baselineGeometrySource ?? 'Nie zapisano'}.
        </p>
        <ul aria-label="Zamrożone wersje zapisanych siatek">
          {result.output.slots.map((slot) => (
            <li key={slot.positionIndex}>
              Plansza {slot.sequenceNumber}:{' '}
              {slot.baselineEngineName ??
                result.baselineEngineName ??
                'Nie zapisano nazwy silnika'}{' '}
              ·{' '}
              {slot.baselineEngineVersion ??
                result.baselineEngineVersion ??
                'Nie zapisano wersji'}
            </li>
          ))}
        </ul>
      </details>
    </section>
  );
}
