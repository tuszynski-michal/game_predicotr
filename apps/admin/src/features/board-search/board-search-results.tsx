'use client';

/* Board crops are local, checksum-verified Admin API assets. */
/* eslint-disable @next/next/no-img-element */

import type { BoardSearchResponse } from '@game-predictor/admin-api-client';
import { type KeyboardEvent, useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  activeBoardSearchResult,
  boardSearchNeighbourIndexes,
  createBoardSearchResultsState,
  moveBoardSearchResult,
} from './board-search-results-state';

type BoardSearchResultsClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  'operationalImageReviewBoardAssetUrl'
>;

interface BoardSearchResultsProps {
  readonly apiBaseUrl: string;
  readonly client?: BoardSearchResultsClient;
  readonly gameId: string;
  readonly response: BoardSearchResponse;
}

export function BoardSearchResults({
  response,
  ...props
}: BoardSearchResultsProps) {
  const resultKey = response.results
    .map((result) => `${result.reviewItemId}:${result.boardChecksumSha256}`)
    .join('|');
  return (
    <BoardSearchResultsCarousel
      key={resultKey}
      response={response}
      {...props}
    />
  );
}

function BoardSearchResultsCarousel({
  apiBaseUrl,
  client,
  gameId,
  response,
}: BoardSearchResultsProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [state, setState] = useState(() =>
    createBoardSearchResultsState(response.results),
  );
  const current = activeBoardSearchResult(state);

  const imageUrl = current
    ? api.operationalImageReviewBoardAssetUrl(current.reviewItemId, {
        gameId,
        importJobId: current.importJobId,
      })
    : null;

  useEffect(() => {
    for (const index of boardSearchNeighbourIndexes(state)) {
      const neighbour = state.results[index];
      if (neighbour === undefined) {
        continue;
      }
      const image = new Image();
      image.src = api.operationalImageReviewBoardAssetUrl(
        neighbour.reviewItemId,
        {
          gameId,
          importJobId: neighbour.importJobId,
        },
      );
    }
  }, [api, gameId, state]);

  function move(direction: -1 | 1) {
    setState((currentState) => moveBoardSearchResult(currentState, direction));
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

      <BoardCrop imageUrl={imageUrl} key={current.reviewItemId} />

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
