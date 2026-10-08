'use client';

/* Board crops are checksum-verified API assets, not Next static media. */
/* eslint-disable @next/next/no-img-element */

import type {
  BoardSearchResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import { type KeyboardEvent, useEffect, useRef, useState } from 'react';

import { unitNoun } from './board-search-approximate-win';
import {
  BoardSearchBoardLinesModal,
  type BoardLinesClient,
} from './board-search-board-lines-modal';
import type {
  BoardSearchDataSource,
  BoardSearchCorrectionContext,
} from './board-search-data-source';
import {
  formatApproximateWinAmount,
  loadApproximateWinDisplay,
  scaleApproximateWinAmount,
} from './board-search-stake';
import {
  activeBoardSearchResult,
  boardSearchNeighbourIndexes,
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
  >;
type BoardSearchResult = BoardSearchResponse['results'][number];

interface BoardSearchResultsProps {
  readonly client: BoardSearchResultsClient;
  readonly gameId: string;
  readonly state: BoardSearchResultsState;
  readonly onStateChange: (state: BoardSearchResultsState) => void;
  /** A cell correction was saved in the board window: search again. */
  readonly onBoardEdited: () => void;
  readonly symbols: readonly SymbolResponse[];
  readonly fixedStakeGrosze?: number;
  readonly correctionContext?: BoardSearchCorrectionContext;
}

export function BoardSearchResults({
  client: api,
  gameId,
  onBoardEdited,
  onStateChange,
  state,
  symbols,
  fixedStakeGrosze,
  correctionContext,
}: BoardSearchResultsProps) {
  const current = activeBoardSearchResult(state);
  const [boardOpen, setBoardOpen] = useState(false);
  const boardTriggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    for (const index of boardSearchNeighbourIndexes(state)) {
      const neighbour = state.results[index];
      if (neighbour === undefined) {
        continue;
      }
      const image = new Image();
      image.src = boardSearchViewUrl(api, gameId, neighbour);
    }
  }, [api, gameId, state]);

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
        <h2>Wyniki wyszukiwania</h2>
        <p>Żadna plansza nie ma dodatniego dopasowania do wskazanego wzoru.</p>
      </section>
    );
  }

  return (
    <section
      aria-label="Wyniki wyszukiwania plansz"
      className="boardSearchResults"
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
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
            <dd>{current.score.score.toFixed(1)}%</dd>
          </div>
          <div>
            <dt>Plansza</dt>
            <dd>#{current.sequenceNumber}</dd>
          </div>
        </dl>
      </header>

      <BoardCrop
        api={api}
        gameId={gameId}
        key={`${current.assetMode}:${current.sequenceNumber}`}
        result={current}
      />

      <dl className="boardSearchEvidence">
        <div>
          <dt>Dokładne</dt>
          <dd>{current.score.exactMatchCount}</dd>
        </div>
        <div>
          <dt>Alternatywy</dt>
          <dd>{current.score.alternativeMatchCount}</dd>
        </div>
        <div>
          <dt>Sprzeczne</dt>
          <dd>{current.score.mismatchCount}</dd>
        </div>
        <div>
          <dt>Brak danych</dt>
          <dd>{current.score.unknownCount}</dd>
        </div>
      </dl>

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
          key={`${current.assetMode}:${current.sequenceNumber}`}
          onClose={(edited) => {
            setBoardOpen(false);
            if (edited) {
              onBoardEdited();
              return;
            }
            boardTriggerRef.current?.focus();
          }}
          onRecalculate={onBoardEdited}
          row={null}
          rulesVersionId={null}
          sequenceNumber={current.sequenceNumber}
          symbols={symbols}
          fixedStakeGrosze={fixedStakeGrosze}
          correctionContext={correctionContext}
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
        <span>Użyj ← / →, aby przejść o jedną planszę.</span>
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

  useEffect(() => {
    cancelledRef.current = false;
    // No reset to null here: this component remounts fully (via the
    // carousel's `key={assetMode:sequenceNumber}`) whenever the displayed
    // board changes, so `quad`/`naturalSize` already start out null for a
    // new board — assigning them again here would be a synchronous
    // setState in the effect body for no behavioural benefit.
    const getReviewItem = api.getOperationalImageReviewItem;
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
  }, [api, gameId, result]);

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
