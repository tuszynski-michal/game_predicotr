'use client';

import type {
  AdminApiClient,
  ImageGeometryCompletenessResponse,
  ImageGridReviewItemResponse,
  IncompleteGeometryImagePageResponse,
  IncompleteGeometryImageResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { apiErrorMessage } from '../catalog/catalog-api-error';

import {
  type BoardGeometryCorrectionTarget,
  deferredBoardGeometryTarget,
  reportedBoardGeometryTarget,
} from './board-geometry-correction-target';
import type { BoardGeometryCorrectionClient } from './board-geometry-correction-workspace';
import {
  BoardGeometryCorrectionEditor,
  type CorrectionSymbol,
} from './deferred-board-cell-geometry-editor';
import {
  GEOMETRY_GAP_STATES_WITHOUT_EDITOR,
  GEOMETRY_GAPS_FILTERS,
  GEOMETRY_GAPS_NO_TARGET_HINT,
  GEOMETRY_GAPS_ROWS_LIMIT,
  geometryGapPositionTarget,
  geometryGapsFilterCount,
  geometryGapsFilterLabel,
  geometryGapsListQuery,
  geometryImageStateLabel,
  geometryImageSummary,
  geometryImageTone,
  geometryImportErrorLabel,
  geometryPositionLabel,
  geometryPositionTone,
  geometrySourceStatusLabel,
  quadCentre,
  quadSvgPoints,
  shouldPrefetchNextPage,
  visibleGapImages,
  type GeometryGapsFilter,
} from './geometry-gaps-state';
import { buildOperationalReviewSymbolShortcuts } from './operational-review-state';

type LoadState = 'error' | 'loading' | 'ready';

export type GeometryGapsClient = BoardGeometryCorrectionClient &
  Pick<
    AdminApiClient,
    | 'getImageGeometryCompleteness'
    | 'getImageGeometryCompletenessSourceAsset'
    | 'listIncompleteGeometryImages'
  >;

interface ImageRows {
  readonly items: readonly ImageGridReviewItemResponse[];
  readonly sourceImageId: string;
}

interface Photo {
  readonly sourceImageId: string;
  readonly url: string;
}

type PageResult =
  | { readonly ok: true; readonly page: IncompleteGeometryImagePageResponse }
  | { readonly error: string; readonly ok: false };

const LIST_ERROR = 'Nie udało się pobrać zdjęć z brakami geometrii.';
const REPORT_ERROR = 'Nie udało się pobrać liczników braków geometrii.';
const ROWS_ERROR = 'Nie udało się sprawdzić celów edycji tego zdjęcia.';
const DISCONNECTED = 'Połączenie z lokalnym Admin API zostało przerwane.';
const NO_EDITOR_HINT =
  'Tego zdjęcia nie da się poprawić w edytorze narożników — przetwórz plik ponownie w Imporcie plansz.';

/**
 * The "Braki zdjęć" tab of the local Reviewer (TASK-0963): one image with a
 * real geometry gap at a time, the real photo under the grids, the state
 * filters of decision 3 and the corner editor of D-462 for one position.
 * The image and position states come from `incomplete-images`; the editing
 * target of a position is its `grid-reviews` row, fetched when the image is
 * opened. The tab never sets gate exceptions nor approves finished grids.
 */
export function GeometryGapsWorkspace({
  api,
  apiBaseUrl,
  gameId,
  keyboardEnabled = true,
}: {
  readonly api: GeometryGapsClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  /** False while a sibling tab is shown; keeps the editor mounted. */
  readonly keyboardEnabled?: boolean;
}) {
  const [filter, setFilter] = useState<GeometryGapsFilter>('all');
  const [showHumanApproved, setShowHumanApproved] = useState(false);
  const [report, setReport] =
    useState<ImageGeometryCompletenessResponse | null>(null);
  const [reportError, setReportError] = useState('');
  const [images, setImages] = useState<
    readonly IncompleteGeometryImageResponse[]
  >([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [listState, setListState] = useState<LoadState>('loading');
  const [listError, setListError] = useState('');
  const [pageError, setPageError] = useState('');
  const [pageLoading, setPageLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [index, setIndex] = useState(0);
  const [notice, setNotice] = useState('');
  const [photo, setPhoto] = useState<Photo | null>(null);
  const [photoState, setPhotoState] = useState<LoadState>('loading');
  const [rows, setRows] = useState<ImageRows | null>(null);
  const [rowsState, setRowsState] = useState<LoadState>('loading');
  const [rowsVersion, setRowsVersion] = useState(0);
  const [editing, setEditing] = useState<number | null>(null);
  const [symbols, setSymbols] = useState<readonly CorrectionSymbol[]>([]);
  const mounted = useRef(true);
  const listRequest = useRef(0);
  const reportRequest = useRef(0);
  const requestedCursor = useRef<string | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    // Without the catalogue the tab still corrects grids; only the symbol
    // picker of the editor stays hidden (same rule as the correction queue).
    void api
      .listSymbols(gameId)
      .then((result) => {
        if (!active || result.error !== undefined || !result.data) return;
        setSymbols(
          buildOperationalReviewSymbolShortcuts(result.data).map(
            ({ key, symbol }) => ({
              id: symbol.id,
              label: symbol.namePl ?? symbol.name,
              shortcut: key,
            }),
          ),
        );
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [api, gameId]);

  const loadReport = useCallback(async () => {
    const current = ++reportRequest.current;
    let result;
    try {
      result = await api.getImageGeometryCompleteness({ gameId });
    } catch {
      result = null;
    }
    if (!mounted.current || current !== reportRequest.current) return;
    if (result === null) {
      setReportError(DISCONNECTED);
      return;
    }
    if (result.error !== undefined || result.data === undefined) {
      setReportError(apiErrorMessage(result.error, REPORT_ERROR));
      return;
    }
    setReport(result.data);
    setReportError('');
  }, [api, gameId]);

  /** One page of the current filter; errors come back as operator text. */
  const fetchPage = useCallback(
    async (afterCursor: string | null): Promise<PageResult> => {
      let result;
      try {
        result = await api.listIncompleteGeometryImages(
          geometryGapsListQuery(gameId, filter, afterCursor),
        );
      } catch {
        return { error: DISCONNECTED, ok: false };
      }
      if (result.error !== undefined || result.data === undefined) {
        return { error: apiErrorMessage(result.error, LIST_ERROR), ok: false };
      }
      return { ok: true, page: result.data };
    },
    [api, filter, gameId],
  );

  /**
   * Loads one page of the list. Without a cursor the queue starts over (the
   * filter changed); with one the page is appended and the images already
   * shown stay navigable while it loads. A failed append keeps the queue and
   * shows a banner with a retry; only a failed first page replaces the view.
   */
  const loadList = useCallback(
    async (afterCursor: string | null): Promise<void> => {
      const current = ++listRequest.current;
      requestedCursor.current = afterCursor;
      if (afterCursor === null) {
        setListState('loading');
        setListError('');
      } else {
        setPageLoading(true);
      }
      setPageError('');
      const result = await fetchPage(afterCursor);
      if (!mounted.current || current !== listRequest.current) return;
      setPageLoading(false);
      if (!result.ok) {
        if (afterCursor === null) {
          setListState('error');
          setListError(result.error);
        } else {
          setPageError(result.error);
        }
        return;
      }
      const page = result.page;
      setImages((previous) =>
        afterCursor === null ? page.images : [...previous, ...page.images],
      );
      setNextCursor(page.nextCursor);
      setListState('ready');
    },
    [fetchPage],
  );

  useEffect(() => {
    queueMicrotask(() => {
      void loadReport();
    });
  }, [loadReport]);

  useEffect(() => {
    queueMicrotask(() => {
      setIndex(0);
      setEditing(null);
      setNotice('');
      void loadList(null);
    });
  }, [loadList]);

  const visible = useMemo(
    () => visibleGapImages(images, showHumanApproved),
    [images, showHumanApproved],
  );
  const hiddenCount = images.length - visible.length;
  const safeIndex = Math.min(index, Math.max(visible.length - 1, 0));
  const current = visible[safeIndex] ?? null;
  const sourceImageId = current?.sourceImageId ?? null;
  const editorAllowed =
    current !== null &&
    !GEOMETRY_GAP_STATES_WITHOUT_EDITOR.has(current.imageState);

  // Near the end of the fetched queue (or when the filter hid everything
  // fetched so far) the next page is fetched ahead of the operator.
  useEffect(() => {
    if (
      listState !== 'ready' ||
      pageLoading ||
      nextCursor === null ||
      requestedCursor.current === nextCursor ||
      !shouldPrefetchNextPage(safeIndex, visible.length, true)
    )
      return;
    queueMicrotask(() => {
      void loadList(nextCursor);
    });
  }, [listState, loadList, nextCursor, pageLoading, safeIndex, visible.length]);

  // The photo loads with the image, without a click; the previous blob URL
  // is revoked when the image changes and when the tab unmounts.
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      if (sourceImageId === null) {
        setPhoto(null);
        return;
      }
      setPhotoState('loading');
      void (async () => {
        let asset;
        try {
          asset = await api.getImageGeometryCompletenessSourceAsset(
            gameId,
            sourceImageId,
          );
        } catch {
          asset = null;
        }
        if (!active) return;
        if (
          asset === null ||
          asset.error !== undefined ||
          !(asset.data instanceof Blob)
        ) {
          setPhotoState('error');
          return;
        }
        setPhoto({ sourceImageId, url: URL.createObjectURL(asset.data) });
        setPhotoState('ready');
      })();
    });
    return () => {
      active = false;
    };
  }, [api, gameId, sourceImageId]);

  useEffect(
    () => () => {
      if (photo !== null) URL.revokeObjectURL(photo.url);
    },
    [photo],
  );

  // The editing targets of the positions: fetched lazily for the open image
  // only, never for the whole page (plan, "Reguły danych").
  useEffect(() => {
    if (sourceImageId === null || !editorAllowed) return;
    let active = true;
    queueMicrotask(() => {
      if (!active) return;
      setRowsState('loading');
      void (async () => {
        let result;
        try {
          result = await api.listImageGridReviews({
            counts: 'correction',
            gameId,
            limit: GEOMETRY_GAPS_ROWS_LIMIT,
            sourceImageId,
            view: 'all',
          });
        } catch {
          result = null;
        }
        if (!active) return;
        if (
          result === null ||
          result.error !== undefined ||
          result.data === undefined
        ) {
          setRowsState('error');
          return;
        }
        setRows({ items: result.data.items, sourceImageId });
        setRowsState('ready');
      })();
    });
    return () => {
      active = false;
    };
  }, [api, editorAllowed, gameId, rowsVersion, sourceImageId]);

  const currentRows =
    rows !== null && rows.sourceImageId === sourceImageId ? rows : null;

  const candidateTarget = useMemo<BoardGeometryCorrectionTarget | null>(() => {
    if (editing === null || currentRows === null) return null;
    const found = geometryGapPositionTarget(currentRows.items, editing);
    if (found === null) return null;
    if (found.kind === 'deferred') {
      return deferredBoardGeometryTarget({
        api,
        apiBaseUrl,
        pendingId: found.pendingId,
        scope: { gameId: found.row.gameId, importJobId: found.row.importJobId },
        symbolsApi: api,
      });
    }
    return reportedBoardGeometryTarget({
      api,
      item: found.row,
      symbolsApi: api,
    });
  }, [api, apiBaseUrl, currentRows, editing]);
  // A refresh rebuilds the rows, but the editor reloads only when the board
  // version (the target key) changed: the same key keeps the same target
  // object, so unsaved corners survive "↻ Odśwież".
  const [stableTarget, setStableTarget] =
    useState<BoardGeometryCorrectionTarget | null>(null);
  if ((candidateTarget?.key ?? null) !== (stableTarget?.key ?? null)) {
    setStableTarget(candidateTarget);
  }
  const target =
    (candidateTarget?.key ?? null) === (stableTarget?.key ?? null)
      ? stableTarget
      : candidateTarget;

  /**
   * Reloads the counters, the targets of the open image and the queue
   * without covering the view: the pages are re-read from the start until
   * the open image is found again (or as many images as before are back),
   * then swapped in at once. The image stays selected by `sourceImageId`;
   * the editor stays mounted (its target key decides whether it reloads).
   */
  const refresh = useCallback(async () => {
    const current = ++listRequest.current;
    requestedCursor.current = null;
    const keep = sourceImageId;
    const previousCount = images.length;
    setRefreshing(true);
    setPageError('');
    setRowsVersion((version) => version + 1);
    void loadReport();
    const collected: IncompleteGeometryImageResponse[] = [];
    let cursor: string | null = null;
    let error: string | null = null;
    let found = false;
    do {
      const result: PageResult = await fetchPage(cursor);
      if (!mounted.current || current !== listRequest.current) return;
      if (!result.ok) {
        error = result.error;
        break;
      }
      collected.push(...result.page.images);
      cursor = result.page.nextCursor;
      found =
        keep !== null &&
        result.page.images.some((image) => image.sourceImageId === keep);
    } while (cursor !== null && !found && collected.length < previousCount);
    setRefreshing(false);
    if (error !== null && collected.length === 0) {
      if (previousCount === 0) {
        setListState('error');
        setListError(error);
      } else {
        // The queue already shown stays; only the banner reports the failure.
        setPageError(error);
      }
      return;
    }
    setImages(collected);
    setNextCursor(cursor);
    setListState('ready');
    setListError('');
    if (error !== null) setPageError(error);
    const position = visibleGapImages(collected, showHumanApproved).findIndex(
      (image) => image.sourceImageId === keep,
    );
    if (position < 0) {
      // The image left the queue (e.g. it became complete).
      setIndex(0);
      setEditing(null);
    } else {
      setIndex(position);
    }
  }, [fetchPage, images.length, loadReport, showHumanApproved, sourceImageId]);

  const handleSaved = useCallback(
    async (reviewItemId: string | null) => {
      setEditing(null);
      setNotice(
        reviewItemId === null
          ? 'Plansza została już rozwiązana przez inną operację. Zdjęcie zostało odświeżone.'
          : 'Siatka zapisana. Zdjęcie i liczniki zostały odświeżone.',
      );
      await refresh();
    },
    [refresh],
  );

  // A conflict closes the editor and reloads the image once; the operator
  // reopens the position, so the same board can never reload in a loop.
  const handleConflict = useCallback(
    async (message: string) => {
      setEditing(null);
      setNotice(
        `${message} Zdjęcie i cele edycji zostały odświeżone — otwórz pozycję ponownie.`,
      );
      await refresh();
    },
    [refresh],
  );

  function selectFilter(next: GeometryGapsFilter) {
    if (next === filter) return;
    setFilter(next);
  }

  function toggleHumanApproved() {
    setShowHumanApproved((value) => !value);
    setIndex(0);
    setEditing(null);
  }

  function showPrevious() {
    setEditing(null);
    setIndex(Math.max(safeIndex - 1, 0));
  }

  function showNext() {
    if (safeIndex >= visible.length - 1) return;
    setEditing(null);
    setIndex(safeIndex + 1);
  }

  const atEnd = safeIndex >= visible.length - 1;

  return (
    <section aria-label="Braki zdjęć" className="deferredGeometryQueue">
      <header className="deferredGeometryHeader geometryGapsHeader">
        <div>
          <span className="eyebrow">Jedno zdjęcie naraz</span>
          <h2>Braki zdjęć</h2>
          <p>
            Zdjęcia z brakującą albo częściową planszą, nieudanym importem lub
            bez geometrii źródła, w zakresie całej gry. Popraw siatkę pozycji,
            która ma planszę albo odroczony slot; pozostałe przetwórz ponownie w
            Imporcie plansz.
          </p>
        </div>
        <button
          aria-busy={refreshing}
          className="secondaryButton"
          disabled={listState === 'loading' || refreshing}
          onClick={() => void refresh()}
          type="button"
        >
          {refreshing ? 'Odświeżam…' : '↻ Odśwież'}
        </button>
      </header>

      <div className="geometryGapsControls">
        <div
          aria-label="Filtr stanu zdjęcia"
          className="operationalReviewViewTabs geometryGapsFilters"
          role="group"
        >
          {GEOMETRY_GAPS_FILTERS.map((name) => (
            <button
              aria-pressed={filter === name}
              key={name}
              onClick={() => selectFilter(name)}
              type="button"
            >
              {geometryGapsFilterLabel(name)}
              {report === null
                ? ''
                : ` (${geometryGapsFilterCount(report, name).toLocaleString('pl-PL')})`}
            </button>
          ))}
        </div>
        <label className="geometryGapsToggle">
          <input
            checked={showHumanApproved}
            onChange={toggleHumanApproved}
            type="checkbox"
          />
          <span>Pokaż także zatwierdzone ręcznie</span>
        </label>
      </div>
      <p className="geometryGapsHint">
        Liczniki przy filtrach to stan w bazie
        {report === null
          ? ''
          : ` (${geometryImageStateLabel('incomplete_partial')}: ${geometryGapsFilterCount(report, 'incomplete_partial').toLocaleString('pl-PL')})`}
        ; lista domyślnie ukrywa zdjęcia, w których wszystkie częściowe plansze
        zatwierdzono ręcznie — przełącznik „Pokaż także zatwierdzone ręcznie”
        obok filtrów.
      </p>

      {reportError ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {reportError}
        </p>
      ) : null}
      {pageError ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {pageError}{' '}
          <button
            className="textButton"
            disabled={pageLoading || refreshing}
            onClick={() =>
              void (nextCursor === null ? refresh() : loadList(nextCursor))
            }
            type="button"
          >
            Ponów pobieranie
          </button>
        </p>
      ) : null}
      {notice ? (
        <p className="operationalReviewNotice" role="status">
          {notice}
        </p>
      ) : null}

      {listState === 'loading' ? (
        <GapsState text="Pobieram zdjęcia z brakami geometrii. Dla całej gry trwa to kilka sekund." />
      ) : listState === 'error' ? (
        <GapsState action={() => void loadList(null)} error text={listError} />
      ) : current === null ? (
        pageLoading ? (
          <GapsState text="Pobieram kolejną stronę zdjęć…" />
        ) : (
          <div className="deferredGeometryComplete">
            <h3>Brak zdjęć w tym stanie</h3>
            <p>
              {hiddenCount > 0
                ? `Ukryto ${hiddenCount.toLocaleString('pl-PL')} zdjęć, których wszystkie częściowe plansze zatwierdzono ręcznie. Włącz „Pokaż także zatwierdzone ręcznie”, aby je zobaczyć.`
                : 'W tym zakresie nie ma zdjęć z realnym brakiem geometrii.'}
            </p>
          </div>
        )
      ) : (
        <article
          aria-label={`Zdjęcie ${current.relativePath}`}
          className="deferredGeometryEditor geometryGapsImage"
        >
          <header className="geometryGapsImageHeader">
            <strong>
              <span title={current.relativePath}>{current.relativePath}</span>
              <span
                className={`geometryStateBadge geometryTone-${geometryImageTone(current.imageState)}`}
              >
                {geometryImageStateLabel(current.imageState)}
              </span>
            </strong>
            <p>
              Status zdjęcia: {geometrySourceStatusLabel(current.sourceStatus)}{' '}
              · {geometryImageSummary(current)}
            </p>
            {current.importErrorCode !== null ? (
              <p className="geometryTone-danger">
                Błąd importu pliku:{' '}
                {geometryImportErrorLabel(current.importErrorCode)}
              </p>
            ) : null}
          </header>

          <GapsPhoto
            image={current}
            photoUrl={photo?.sourceImageId === sourceImageId ? photo.url : null}
            state={photoState}
          />

          {editorAllowed ? null : (
            <p className="geometryGapsHint">{NO_EDITOR_HINT}</p>
          )}
          {editorAllowed && rowsState === 'loading' ? (
            <p className="geometryGapsHint" role="status">
              Sprawdzam cele edycji pozycji…
            </p>
          ) : null}
          {editorAllowed && rowsState === 'error' ? (
            <p className="feedbackBanner feedbackBannerError" role="alert">
              {ROWS_ERROR}{' '}
              <button
                className="textButton"
                onClick={() => setRowsVersion((version) => version + 1)}
                type="button"
              >
                Spróbuj ponownie
              </button>
            </p>
          ) : null}

          {current.positions.length > 0 ? (
            <ul className="geometryPositionList geometryGapsPositions">
              {current.positions.map((position) => {
                const tone = geometryPositionTone(position.state);
                const positionTarget =
                  editorAllowed && currentRows !== null
                    ? geometryGapPositionTarget(
                        currentRows.items,
                        position.positionIndex,
                      )
                    : null;
                return (
                  <li
                    className={`geometryPositionChip geometryTone-${tone}`}
                    key={position.positionIndex}
                  >
                    <span>
                      {position.positionIndex + 1}. #
                      {position.sequenceNumber.toLocaleString('pl-PL')}
                    </span>
                    <span>
                      {geometryPositionLabel(
                        position.state,
                        position.reasonCode,
                      )}
                      {position.quad === null || position.quad === undefined
                        ? ' · bez siatki'
                        : ''}
                    </span>
                    {position.humanApproved === true ? (
                      <span className="geometryGapsApproved">
                        zatwierdzona ręcznie
                      </span>
                    ) : null}
                    {positionTarget !== null ? (
                      <button
                        aria-pressed={editing === position.positionIndex}
                        className="secondaryButton"
                        // Stale rows cannot open a target while fresh ones load.
                        disabled={rowsState === 'loading'}
                        onClick={() =>
                          setEditing((value) =>
                            value === position.positionIndex
                              ? null
                              : position.positionIndex,
                          )
                        }
                        type="button"
                      >
                        {editing === position.positionIndex
                          ? 'Zamknij edytor'
                          : 'Popraw siatkę tej planszy'}
                      </button>
                    ) : editorAllowed && currentRows !== null ? (
                      <small>{GEOMETRY_GAPS_NO_TARGET_HINT}</small>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="geometryGapsHint">
              Zdjęcie nie ma pozycji plansz do pokazania.
            </p>
          )}

          {target !== null ? (
            <BoardGeometryCorrectionEditor
              key={target.key}
              keyboardEnabled={keyboardEnabled}
              onConflict={handleConflict}
              onSaved={handleSaved}
              saveLabel="Zapisz siatkę pozycji"
              symbols={symbols}
              target={target}
            />
          ) : null}

          <footer className="deferredGeometryNavigation">
            <button
              className="secondaryButton"
              disabled={safeIndex === 0}
              onClick={showPrevious}
              type="button"
            >
              ← Poprzednie
            </button>
            <span>
              Zdjęcie <strong>{(safeIndex + 1).toLocaleString('pl-PL')}</strong>{' '}
              z {visible.length.toLocaleString('pl-PL')}
              {nextCursor !== null ? '+' : ''}
              {hiddenCount > 0 && !showHumanApproved
                ? ` · ukryte zatwierdzone ręcznie: ${hiddenCount.toLocaleString('pl-PL')}`
                : ''}
            </span>
            <button
              className="secondaryButton"
              disabled={atEnd}
              onClick={showNext}
              type="button"
            >
              {atEnd && pageLoading ? 'Ładowanie…' : 'Następne →'}
            </button>
          </footer>
        </article>
      )}
    </section>
  );
}

/** The real photo with the grids of the positions drawn over it. */
function GapsPhoto({
  image,
  photoUrl,
  state,
}: {
  readonly image: IncompleteGeometryImageResponse;
  readonly photoUrl: string | null;
  readonly state: LoadState;
}) {
  const width = image.orientedWidth;
  const height = image.orientedHeight;
  const canDraw =
    width !== null && height !== null && image.positions.length > 0;
  const fontSize = width === null ? 12 : Math.max(12, Math.round(width / 45));
  const strokeWidth = width === null ? 2 : Math.max(2, Math.round(width / 400));
  return (
    <div className="geometryGapsPhoto">
      {canDraw ? (
        <svg
          aria-label={`Zdjęcie ${image.relativePath} z naniesionymi siatkami plansz`}
          className="geometryPreview"
          role="img"
          viewBox={`0 0 ${width} ${height}`}
        >
          <rect fill="rgba(255,255,255,0.04)" height={height} width={width} />
          {photoUrl !== null ? (
            <image
              height={height}
              href={photoUrl}
              preserveAspectRatio="none"
              width={width}
            />
          ) : null}
          {image.positions.map((position) => {
            const points = quadSvgPoints(position.quad);
            if (points === null || !position.quad) return null;
            const centre = quadCentre(position.quad);
            const tone = geometryPositionTone(position.state);
            return (
              <g
                className={`geometryQuad geometryTone-${tone}`}
                key={position.positionIndex}
              >
                <polygon
                  fill="none"
                  points={points}
                  strokeDasharray={tone === 'danger' ? '12 8' : undefined}
                  strokeWidth={strokeWidth}
                />
                <text
                  fontSize={fontSize}
                  textAnchor="middle"
                  x={centre.x}
                  y={centre.y}
                >
                  {position.positionIndex + 1}
                </text>
              </g>
            );
          })}
        </svg>
      ) : photoUrl !== null ? (
        // eslint-disable-next-line @next/next/no-img-element -- a blob URL of the checksum-bound source image
        <img
          alt={`Zdjęcie ${image.relativePath}`}
          className="geometryPreview"
          src={photoUrl}
        />
      ) : null}
      {state === 'loading' ? (
        <small className="geometryGapsPhotoStatus">Pobieram zdjęcie…</small>
      ) : null}
      {state === 'error' ? (
        <small className="geometryTone-danger">
          Zdjęcie źródłowe jest niedostępne.
        </small>
      ) : null}
    </div>
  );
}

function GapsState({
  action,
  error = false,
  text,
}: {
  readonly action?: () => void;
  readonly error?: boolean;
  readonly text: string;
}) {
  return (
    <div className={error ? 'emptyState errorState' : 'emptyState'}>
      <h3>
        {error ? 'Nie udało się wczytać braków zdjęć' : 'Wczytywanie braków'}
      </h3>
      <p>{text}</p>
      {action ? (
        <button className="secondaryButton" onClick={action} type="button">
          Spróbuj ponownie
        </button>
      ) : null}
    </div>
  );
}
