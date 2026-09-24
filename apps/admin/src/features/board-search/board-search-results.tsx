'use client';

/* Board crops are local, checksum-verified Admin API assets. */
/* eslint-disable @next/next/no-img-element */

import type { BoardSearchResponse } from '@game-predictor/admin-api-client';
import { type KeyboardEvent, useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  activeBoardSearchResult,
  boardSearchNeighbourIndexes,
  moveBoardSearchResult,
  type BoardSearchResultsState,
} from './board-search-results-state';

type BoardSearchResultsClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  'archivedBoardSearchAssetUrl' | 'operationalImageReviewBoardAssetUrl'
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
        imageUrl={imageUrl}
        key={`${current.assetMode}:${current.sequenceNumber}`}
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

function BoardCrop({ imageUrl }: { readonly imageUrl: string }) {
  const [failed, setFailed] = useState(false);
  if (failed) {
    return (
      <div className="boardSearchBoardAssetError" role="alert">
        Crop tej planszy nie jest obecnie dostępny. Wynik wyszukiwania pozostaje
        poprawny — wybierz sąsiedni wynik albo sprawdź artefakty importu.
      </div>
    );
  }
  return (
    <img
      alt="Pełny crop znalezionej planszy"
      className="boardSearchBoardAsset"
      onError={() => setFailed(true)}
      src={imageUrl}
    />
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
