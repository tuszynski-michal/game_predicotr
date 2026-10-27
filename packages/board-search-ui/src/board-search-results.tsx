'use client';

/* Board crops are checksum-verified API assets, not Next static media. */
/* eslint-disable @next/next/no-img-element */

import type {
  BoardSearchResponse,
  BoardSearchSequenceResultResponse,
  SuperGameStateResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { type KeyboardEvent, useEffect, useRef, useState } from 'react';

import { unitNoun } from './board-search-approximate-win';
import { BoardSearchPhotoNavigation } from './board-search-photo-navigation';
import {
  BoardSearchBoardLinesModal,
  type BoardLinesClient,
} from './board-search-board-lines-modal';
import type {
  BoardSearchDataSource,
  BoardSearchCorrectionContext,
} from './board-search-data-source';
import type { BoardSearchRulesVersionOption } from './board-search-rules-versions';
import {
  SuperGameMarkerBadge,
  SuperGameStateBanner,
} from './board-search-super-game-marker';
import {
  formatApproximateWinAmount,
  loadApproximateWinDisplay,
  scaleApproximateWinAmount,
} from './board-search-stake';
import {
  activeBoardSearchResult,
  boardSearchNeighbourIndexes,
  boardSearchResultIdentity,
  computeBoardCropTransform,
  moveBoardSearchResult,
  parseBoardCropQuad,
  type BoardCropTransform,
  type BoardSearchResultsState,
} from './board-search-results-state';

type BoardSearchResultsClient = BoardLinesClient &
  Pick<
    BoardSearchDataSource,
    | 'boardSearchBoardViewUrl'
    | 'getOperationalImageReviewItem'
    | 'operationalImageReviewBoardAssetUrl'
    | 'superGameSeriesHref'
  >;
type BoardSearchResult = BoardSearchResponse['results'][number];

interface BoardSearchResultsProps {
  readonly photoNavigation?: boolean;
  readonly photoRevision?: number;
  readonly sequenceResult?: BoardSearchSequenceResultResponse | null;
  readonly compact?: boolean;
  readonly client: BoardSearchResultsClient;
  readonly gameId: string;
  readonly state: BoardSearchResultsState;
  readonly onStateChange: (state: BoardSearchResultsState) => void;
  /** A cell correction was saved in the board window: search again. */
  readonly onBoardEdited: () => void;
  readonly symbols: readonly SymbolResponse[];
  readonly fixedStakeGrosze?: number;
  readonly correctionContext?: BoardSearchCorrectionContext;
  /** Admin-only „Wersja reguł” choice in the board window (D-535). */
  readonly rulesVersions?: readonly BoardSearchRulesVersionOption[] | null;
  /** Freshness of the series generation behind the markers (TASK-0935). */
  readonly superGameState?: SuperGameStateResponse | null;
  /** Opens the series of the marked board in place (online share, D-564). */
  readonly onOpenSuperGameSeries?: (
    seriesId: string,
    sequenceNumber: number,
  ) => void;
}

export function BoardSearchResults({
  photoNavigation = false,
  photoRevision = 0,
  sequenceResult = null,
  compact = false,
  client: api,
  gameId,
  onBoardEdited,
  onOpenSuperGameSeries,
  onStateChange,
  state,
  symbols,
  fixedStakeGrosze,
  correctionContext,
  rulesVersions = null,
  superGameState = null,
}: BoardSearchResultsProps) {
  const current = activeBoardSearchResult(state);
  const evidenceScore = sequenceResult?.score ?? current?.score;
  const [boardOpen, setBoardOpen] = useState(false);
  const [detailSequence, setDetailSequence] = useState<number | null>(null);
  const boardTriggerRef = useRef<HTMLButtonElement>(null);
  const boardViewUrl = api.boardSearchBoardViewUrl;

  useEffect(() => {
    for (const index of boardSearchNeighbourIndexes(state)) {
      const neighbour = state.results[index];
      if (neighbour === undefined) {
        continue;
      }
      const image = new Image();
      image.src = boardViewUrl(
        gameId,
        neighbour.sequenceNumber,
        neighbour.boardChecksumSha256,
      );
    }
  }, [boardViewUrl, gameId, state]);

  function move(direction: -1 | 1) {
    onStateChange(moveBoardSearchResult(state, direction));
  }

  function handleKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      move(-1);
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      move(1);
    }
  }

  if (current === null) {
    return (
      <section className="boardSearchResults" aria-live="polite">
        <SuperGameStateBanner state={superGameState} />
        <h2>Wyniki wyszukiwania</h2>
        <p>Żadna plansza nie ma dodatniego dopasowania do wskazanego wzoru.</p>
      </section>
    );
  }

  return (
    <section
      aria-label="Wyniki wyszukiwania plansz"
      className={
        current.superGame
          ? 'boardSearchResults boardSearchResultsSuperGame'
          : 'boardSearchResults'
      }
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      <SuperGameStateBanner state={superGameState} />
      <header>
        <div>
          <p className="eyebrow">Wyniki wyszukiwania</p>
          <h2>
            {state.activeIndex + 1} z {state.results.length}
          </h2>
        </div>
        <dl className="boardSearchResultMetrics">
          <div>
            <dt>Dopasowanie</dt>
            <dd>
              {(sequenceResult?.score.score ?? current.score.score).toFixed(1)}%
            </dd>
          </div>
          <div>
            <dt>{sequenceResult === null ? 'Plansza' : 'Ciąg'}</dt>
            <dd>
              {sequenceResult === null
                ? `#${current.sequenceNumber}`
                : `#${sequenceResult.startSequenceNumber} → #${sequenceResult.endSequenceNumber}`}
            </dd>
          </div>
        </dl>
      </header>

      {sequenceResult !== null ? (
        <div
          className="boardSearchSequenceResults"
          aria-label="Plansze dopasowanego ciągu"
        >
          {sequenceResult.boards.map((board, index) => (
            <span
              className="boardSearchSequenceBoard"
              key={board.sequenceNumber}
            >
              <button
                className="secondaryButton"
                type="button"
                key={board.sequenceNumber}
                onClick={() => {
                  setDetailSequence(board.sequenceNumber);
                  setBoardOpen(true);
                }}
              >
                Układ {index + 1}: #{board.sequenceNumber} ·{' '}
                {board.score.score.toFixed(1)}%
              </button>
              {index < sequenceResult.boards.length - 1 && board.superGame ? (
                <SuperGameMarkerBadge
                  gameId={gameId}
                  marker={board.superGame}
                  seriesHref={api.superGameSeriesHref}
                  onOpenSeries={
                    onOpenSuperGameSeries === undefined
                      ? undefined
                      : (seriesId) =>
                          onOpenSuperGameSeries(seriesId, board.sequenceNumber)
                  }
                />
              ) : null}
            </span>
          ))}
          <small>
            Wygrane od ostatniej planszy: #{sequenceResult.endSequenceNumber}.
          </small>
        </div>
      ) : null}

      {evidenceScore?.unknownMatchesAll && evidenceScore.unknownCount > 0 ? (
        <p className="boardSearchUnknownWarning" role="status">
          Nierozpoznane symbole: {evidenceScore.unknownCount}. Pasują do
          dowolnego symbolu.
        </p>
      ) : null}

      {!photoNavigation && current.superGame ? (
        <SuperGameMarkerBadge
          gameId={gameId}
          marker={current.superGame}
          onOpenSeries={
            onOpenSuperGameSeries === undefined
              ? undefined
              : (seriesId) =>
                  onOpenSuperGameSeries(seriesId, current.sequenceNumber)
          }
          seriesHref={api.superGameSeriesHref}
        />
      ) : null}

      {compact ? (
        <div
          className="boardSearchCompactResults"
          aria-label="Wybierz planszę startową"
        >
          {state.results.map((result, index) => (
            <button
              type="button"
              key={result.sequenceNumber}
              aria-pressed={index === state.activeIndex}
              onClick={() => onStateChange({ ...state, activeIndex: index })}
            >
              Plansza #{result.sequenceNumber} · {result.score.score.toFixed(1)}
              %
            </button>
          ))}
        </div>
      ) : null}
      {photoNavigation ? (
        <BoardSearchPhotoNavigation
          key={`${gameId}:${sequenceResult?.startSequenceNumber ?? current.sequenceNumber}:${boardSearchResultIdentity(current)}:${photoRevision}`}
          api={api}
          gameId={gameId}
          boards={sequenceResult?.boards ?? [current]}
          openButtonRef={boardTriggerRef}
          onOpenBoard={(sequenceNumber) => {
            setDetailSequence(sequenceNumber);
            setBoardOpen(true);
          }}
          renderBoard={(board) => (
            <>
              {board.superGame ? (
                <SuperGameMarkerBadge
                  gameId={gameId}
                  marker={board.superGame}
                  seriesHref={api.superGameSeriesHref}
                  onOpenSeries={
                    onOpenSuperGameSeries === undefined
                      ? undefined
                      : (seriesId) =>
                          onOpenSuperGameSeries(seriesId, board.sequenceNumber)
                  }
                />
              ) : null}
              <BoardCrop
                api={api}
                gameId={gameId}
                key={`crop:${gameId}:${boardSearchResultIdentity(board)}`}
                result={board}
              />
            </>
          )}
        />
      ) : compact ? (
        <button
          className="boardSearchCompactBoard"
          type="button"
          aria-label={`Pokaż planszę #${current.sequenceNumber} z liniami wypłat`}
          onClick={() => setBoardOpen(true)}
          ref={boardTriggerRef}
        >
          <BoardCrop
            api={api}
            gameId={gameId}
            key={`crop:${gameId}:${boardSearchResultIdentity(current)}`}
            result={current}
          />
        </button>
      ) : (
        <BoardCrop
          api={api}
          gameId={gameId}
          key={`crop:${gameId}:${boardSearchResultIdentity(current)}`}
          result={current}
        />
      )}

      <dl className="boardSearchEvidence">
        <div>
          <dt>Dokładne</dt>
          <dd>{evidenceScore?.exactMatchCount}</dd>
        </div>
        <div>
          <dt>Alternatywy</dt>
          <dd>{evidenceScore?.alternativeMatchCount}</dd>
        </div>
        <div>
          <dt>Sprzeczne</dt>
          <dd>{evidenceScore?.mismatchCount}</dd>
        </div>
        <div>
          <dt>Brak danych</dt>
          <dd>{evidenceScore?.unknownCount}</dd>
        </div>
      </dl>

      {compact || photoNavigation ? null : (
        <div className="boardSearchResultNavigation">
          <button
            aria-label={`Pokaż planszę #${current.sequenceNumber} z liniami wypłat`}
            className="secondaryButton"
            onClick={() => setBoardOpen(true)}
            ref={boardTriggerRef}
            type="button"
          >
            Pokaż planszę
          </button>
          <span>
            Otwiera planszę z liniami wypłat; w oknie możesz poprawić pola.
          </span>
        </div>
      )}

      {boardOpen ? (
        <BoardSearchBoardLinesModal
          api={api}
          formatAmount={(credits) => {
            const display = loadApproximateWinDisplay();
            // Base stake: credits x 10 grosze, whatever the spin cost is.
            return `${formatApproximateWinAmount(
              scaleApproximateWinAmount(credits, display, 0),
              display.unit,
            )}${unitNoun(display.unit)}`;
          }}
          gameId={gameId}
          key={`detail:${gameId}:${detailSequence ?? current.sequenceNumber}:${boardSearchResultIdentity(current)}`}
          onClose={(edited) => {
            setBoardOpen(false);
            setDetailSequence(null);
            if (edited) {
              onBoardEdited();
              return;
            }
            boardTriggerRef.current?.focus();
          }}
          onRecalculate={onBoardEdited}
          row={null}
          rulesVersionId={null}
          rulesVersions={rulesVersions}
          sequenceNumber={detailSequence ?? current.sequenceNumber}
          symbols={symbols}
          fixedStakeGrosze={fixedStakeGrosze}
          correctionContext={
            !photoNavigation && sequenceResult === null
              ? correctionContext
              : {
                  startSequenceNumber: detailSequence ?? current.sequenceNumber,
                }
          }
        />
      ) : null}

      <footer className="boardSearchResultNavigation">
        <button
          className="secondaryButton"
          disabled={state.activeIndex === 0}
          onClick={() => move(-1)}
          type="button"
        >
          ← Poprzednia
        </button>
        <span>Użyj ← / →, aby przejść do innego dopasowania.</span>
        <button
          className="secondaryButton"
          disabled={state.activeIndex >= state.results.length - 1}
          onClick={() => move(1)}
          type="button"
        >
          Następna →
        </button>
      </footer>
    </section>
  );
}

/** The server-side crop around the board (TASK-0763): small and cacheable. */
function boardSearchViewUrl(
  api: BoardSearchResultsClient,
  gameId: string,
  result: BoardSearchResult,
): string {
  return api.boardSearchBoardViewUrl(
    gameId,
    result.sequenceNumber,
    result.boardChecksumSha256,
  );
}

/**
 * The whole stored photo, used only when the cropped view is unavailable
 * (for example a stale search reading, which the view rejects). `null` when
 * the data source has no such asset (online share) or the result has none.
 */
function boardSearchFullAssetUrl(
  api: BoardSearchResultsClient,
  gameId: string,
  result: BoardSearchResult,
): string | null {
  if (result.reviewItemId === null || result.importJobId === null) {
    return null;
  }
  return (
    api.operationalImageReviewBoardAssetUrl?.(result.reviewItemId, {
      gameId,
      importJobId: result.importJobId,
    }) ?? null
  );
}

function BoardCrop({
  api,
  gameId,
  result,
}: {
  readonly api: BoardSearchResultsClient;
  readonly gameId: string;
  readonly result: BoardSearchResult;
}) {
  const [viewFailed, setViewFailed] = useState(false);
  const fullImageUrl = viewFailed
    ? boardSearchFullAssetUrl(api, gameId, result)
    : null;

  if (!viewFailed) {
    return (
      <img
        alt="Kadr zdjęcia wokół znalezionej planszy"
        className="boardSearchBoardAsset"
        onError={() => setViewFailed(true)}
        src={boardSearchViewUrl(api, gameId, result)}
      />
    );
  }
  if (fullImageUrl === null) {
    return <BoardAssetError />;
  }
  return (
    <FullPhotoCrop
      api={api}
      gameId={gameId}
      imageUrl={fullImageUrl}
      result={result}
    />
  );
}

function BoardAssetError() {
  return (
    <div className="boardSearchBoardAssetError" role="alert">
      Crop tej planszy nie jest obecnie dostępny. Wynik wyszukiwania pozostaje
      poprawny — wybierz sąsiedni wynik albo sprawdź artefakty importu.
    </div>
  );
}

/** Fallback: the whole photo framed around the board with CSS. */
function FullPhotoCrop({
  api,
  gameId,
  imageUrl,
  result,
}: {
  readonly api: BoardSearchResultsClient;
  readonly gameId: string;
  readonly imageUrl: string;
  readonly result: BoardSearchResult;
}) {
  const [failed, setFailed] = useState(false);
  // The whole source photo is framed with the board's saved geometry
  // (virtual geometry storage has no persistent per-board bitmap).
  const [quad, setQuad] = useState<ReturnType<typeof parseBoardCropQuad>>(null);
  const [naturalSize, setNaturalSize] = useState<{
    readonly width: number;
    readonly height: number;
  } | null>(null);
  const cancelledRef = useRef(false);
  const getReviewItem = api.getOperationalImageReviewItem;

  useEffect(() => {
    cancelledRef.current = false;
    // No reset to null here: this component remounts fully (via the
    // carousel's crop key) whenever the displayed game, board or checksum
    // changes, so `quad`/`naturalSize` already start out null for a
    // new board — assigning them again here would be a synchronous
    // setState in the effect body for no behavioural benefit.
    if (
      result.reviewItemId === null ||
      result.importJobId === null ||
      getReviewItem === undefined
    ) {
      return () => {
        cancelledRef.current = true;
      };
    }
    void getReviewItem(result.reviewItemId, {
      gameId,
      importJobId: result.importJobId,
    })
      .then((response) => {
        if (cancelledRef.current) {
          return;
        }
        const parsed =
          response.data !== undefined
            ? parseBoardCropQuad(response.data.geometry)
            : null;
        setQuad(parsed);
      })
      .catch(() => {
        // Purely cosmetic: a failed geometry fetch just keeps the full,
        // unmodified image instead of blocking a valid search result.
      });
    return () => {
      cancelledRef.current = true;
    };
  }, [getReviewItem, gameId, result]);

  if (failed) {
    return <BoardAssetError />;
  }

  const transform: BoardCropTransform | null =
    quad !== null && naturalSize !== null
      ? computeBoardCropTransform(quad, naturalSize.width, naturalSize.height)
      : null;

  if (transform === null) {
    return (
      <img
        alt="Pełny crop znalezionej planszy"
        className="boardSearchBoardAsset"
        onError={() => setFailed(true)}
        onLoad={(event) =>
          setNaturalSize({
            height: event.currentTarget.naturalHeight,
            width: event.currentTarget.naturalWidth,
          })
        }
        src={imageUrl}
      />
    );
  }

  return (
    <div
      className="boardSearchBoardAssetFrame"
      style={{
        aspectRatio: `${transform.aspectRatioWidth} / ${transform.aspectRatioHeight}`,
      }}
    >
      <img
        alt="Kadrowany fragment zdjęcia wokół znalezionej planszy"
        className="boardSearchBoardAsset boardSearchBoardAssetCropped"
        onError={() => setFailed(true)}
        src={imageUrl}
        style={{
          height: `${transform.imageHeightPercent}%`,
          left: `${transform.imageLeftPercent}%`,
          top: `${transform.imageTopPercent}%`,
          width: `${transform.imageWidthPercent}%`,
        }}
      />
    </div>
  );
}
