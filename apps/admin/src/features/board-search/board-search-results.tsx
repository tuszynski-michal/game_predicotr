'use client';

/* Board crops are local, checksum-verified Admin API assets. */
/* eslint-disable @next/next/no-img-element */

import type { BoardSearchResponse } from '@game-predictor/admin-api-client';
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  activeBoardSearchResult,
  boardSearchNeighbourIndexes,
  computeBoardCropTransform,
  moveBoardSearchResult,
  parseBoardCropQuad,
  type BoardCropTransform,
  type BoardSearchResultsState,
} from './board-search-results-state';

type BoardSearchResultsClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  | 'archivedBoardSearchAssetUrl'
  | 'getOperationalImageReviewItem'
  | 'operationalImageReviewBoardAssetUrl'
>;

interface BoardSearchResultsProps {
  readonly apiBaseUrl: string;
  readonly client?: BoardSearchResultsClient;
  readonly gameId: string;
  readonly state: BoardSearchResultsState;
  readonly onStateChange: (state: BoardSearchResultsState) => void;
}

export function BoardSearchResults({
  apiBaseUrl,
  client,
  gameId,
  onStateChange,
  state,
}: BoardSearchResultsProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const current = activeBoardSearchResult(state);

  const imageUrl = current ? boardSearchAssetUrl(api, gameId, current) : null;

  useEffect(() => {
    for (const index of boardSearchNeighbourIndexes(state)) {
      const neighbour = state.results[index];
      if (neighbour === undefined) {
        continue;
      }
      const neighbourUrl = boardSearchAssetUrl(api, gameId, neighbour);
      if (neighbourUrl !== null) {
        const image = new Image();
        image.src = neighbourUrl;
      }
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

  if (current === null || imageUrl === null) {
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
            <dt>Status</dt>
            <dd>{statusLabel(current.status)}</dd>
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
        imageUrl={imageUrl}
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

function boardSearchAssetUrl(
  api: BoardSearchResultsClient,
  gameId: string,
  result: BoardSearchResponse['results'][number],
): string | null {
  if (result.assetMode === 'legacy_archive') {
    return api.archivedBoardSearchAssetUrl(
      gameId,
      result.sequenceNumber,
      result.boardChecksumSha256,
    );
  }
  if (result.reviewItemId === null || result.importJobId === null) {
    return null;
  }
  return api.operationalImageReviewBoardAssetUrl(result.reviewItemId, {
    gameId,
    importJobId: result.importJobId,
  });
}

function BoardCrop({
  api,
  gameId,
  imageUrl,
  result,
}: {
  readonly api: BoardSearchResultsClient;
  readonly gameId: string;
  readonly imageUrl: string;
  readonly result: BoardSearchResponse['results'][number];
}) {
  const [failed, setFailed] = useState(false);
  // Only `operational_review` boards can be the whole source photo (virtual
  // geometry storage has no persistent per-board bitmap); `legacy_archive`
  // already serves a single-board image, so it never needs this and never
  // issues the extra request.
  const [quad, setQuad] = useState<ReturnType<typeof parseBoardCropQuad>>(
    null,
  );
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
    if (
      result.assetMode !== 'operational_review' ||
      result.reviewItemId === null ||
      result.importJobId === null
    ) {
      return () => {
        cancelledRef.current = true;
      };
    }
    void api
      .getOperationalImageReviewItem(result.reviewItemId, {
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
    return (
      <div className="boardSearchBoardAssetError" role="alert">
        Crop tej planszy nie jest obecnie dostępny. Wynik wyszukiwania pozostaje
        poprawny — wybierz sąsiedni wynik albo sprawdź artefakty importu.
      </div>
    );
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

function statusLabel(status: string): string {
  switch (status) {
    case 'accepted':
      return 'Zatwierdzona';
    case 'corrected':
      return 'Poprawiona';
    case 'pending':
      return 'Oczekuje';
    default:
      return status;
  }
}
