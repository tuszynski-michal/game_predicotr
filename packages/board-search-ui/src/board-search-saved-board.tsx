'use client';
/* Protected board assets are API images. */
/* eslint-disable @next/next/no-img-element */
import { useEffect, useState } from 'react';
import type {
  BoardSearchDataSource,
  BoardSearchModalDetail,
} from './board-search-data-source';
import { apiErrorMessage } from './api-error';

/** Read an explicit trusted saved sequence; never derive it from ranked hits. */
export function BoardSearchSavedBoard({
  client,
  gameId,
  sequenceNumber,
  onOpen,
}: {
  readonly client: BoardSearchDataSource;
  readonly gameId: string;
  readonly sequenceNumber: number;
  readonly onOpen: () => void;
}) {
  const [detail, setDetail] = useState<BoardSearchModalDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    void client
      .getBoardSearchBoardDetail(gameId, sequenceNumber)
      .then((response) => {
        if (!active) return;
        if (response.error !== undefined || response.data === undefined) {
          setError(
            apiErrorMessage(
              response.error,
              'Nie udało się wczytać zapisanej planszy. Jej pozycja pozostaje zachowana.',
            ),
          );
          return;
        }
        setDetail(response.data);
      })
      .catch(() => {
        if (active)
          setError(
            'Nie udało się wczytać zapisanej planszy. Jej pozycja pozostaje zachowana.',
          );
      });
    return () => {
      active = false;
    };
  }, [client, gameId, sequenceNumber]);
  return (
    <section
      aria-label="Zapisana plansza startowa"
      className="boardSearchResults"
    >
      <h2>Zapisana plansza startowa #{sequenceNumber}</h2>
      {detail?.view ? (
        <img
          alt={`Zapisana plansza ${sequenceNumber}`}
          style={{ maxWidth: '100%', maxHeight: 300 }}
          src={client.boardSearchBoardViewUrl(
            gameId,
            sequenceNumber,
            detail.boardChecksumSha256,
            detail.view.revision,
          )}
        />
      ) : null}
      {error ? (
        <p role="alert">{error}</p>
      ) : detail === null ? (
        <p role="status">Wczytywanie zapisanej planszy…</p>
      ) : null}
      <button className="secondaryButton" type="button" onClick={onOpen}>
        Pokaż zapisaną planszę
      </button>
    </section>
  );
}
