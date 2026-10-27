'use client';

/* Protected board crops are checksum-bound API assets. */
/* eslint-disable @next/next/no-img-element */
import { useEffect, useRef, useState, type ReactNode, type Ref } from 'react';
import type { BoardSearchResponse } from '@game-predictor/admin-api-client';
import type {
  BoardSearchDataSource,
  BoardSearchModalDetail,
} from './board-search-data-source';
import { apiErrorMessage } from './api-error';

type Board = BoardSearchResponse['results'][number];
type PhotoClient = Pick<
  BoardSearchDataSource,
  'getBoardSearchBoardDetail' | 'boardSearchBoardViewUrl'
>;

/** Mounted per selected search result: browsing never moves the win anchor. */
export function BoardSearchPhotoNavigation({
  api,
  gameId,
  boards,
  renderBoard,
  onOpenBoard,
  openButtonRef,
}: {
  readonly api: PhotoClient;
  readonly gameId: string;
  readonly boards: readonly Board[];
  readonly renderBoard: (board: Board) => ReactNode;
  readonly onOpenBoard: (sequenceNumber: number) => void;
  readonly openButtonRef: Ref<HTMLButtonElement>;
}) {
  const [index, setIndex] = useState(0);
  const [adjacent, setAdjacent] = useState<
    ReadonlyMap<number, BoardSearchModalDetail>
  >(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef(true);
  const pending = useRef(false);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const matched = boards[index];
  const detail = adjacent.get(index);
  const sequenceNumber = matched?.sequenceNumber ?? detail?.sequenceNumber;
  const minIndex = -Math.min(15, boards[0].sequenceNumber - 1);
  const maxIndex = boards.length + 15 - 1;
  const total = maxIndex - minIndex + 1;

  async function move(direction: -1 | 1) {
    const nextIndex = index + direction;
    if (pending.current || nextIndex < minIndex || nextIndex > maxIndex) return;
    setError(null);
    if (boards[nextIndex] !== undefined || adjacent.has(nextIndex)) {
      setIndex(nextIndex);
      return;
    }
    const requested =
      nextIndex < 0
        ? boards[0].sequenceNumber + nextIndex
        : boards[boards.length - 1].sequenceNumber +
          nextIndex -
          boards.length +
          1;
    pending.current = true;
    setLoading(true);
    try {
      const response = await api.getBoardSearchBoardDetail(gameId, requested);
      if (!active.current) return;
      if (response.error !== undefined || response.data === undefined) {
        throw new Error(
          apiErrorMessage(
            response.error,
            `Nie udało się wczytać planszy #${requested}.`,
          ),
        );
      }
      if (
        response.data.sequenceNumber !== requested ||
        response.data.documentStale
      ) {
        throw new Error(
          `Odczyt planszy #${requested} jest nieaktualny lub nieprawidłowy.`,
        );
      }
      const data = response.data;
      setAdjacent((previous) => new Map(previous).set(nextIndex, data));
      setIndex(nextIndex);
    } catch (cause: unknown) {
      if (active.current)
        setError(
          `${cause instanceof Error ? cause.message : apiErrorMessage(cause, `Nie udało się wczytać planszy #${requested}.`)} Dotychczasowe zdjęcie pozostaje widoczne. Kliknij „${direction === 1 ? 'Następny układ' : 'Poprzedni układ'}”, aby ponowić.`,
        );
    } finally {
      pending.current = false;
      if (active.current) setLoading(false);
    }
  }

  return (
    <div
      className="boardSearchPhotoNavigation"
      aria-label="Przegląd zdjęć dopasowania"
      aria-busy={loading}
    >
      <p role="status">
        Zdjęcie #{sequenceNumber} · {index - minIndex + 1} z {total}
        {matched
          ? ` · Układ ${index + 1} dopasowania · ${matched.score.score.toFixed(1)}%`
          : index < 0
            ? ' · Przed dopasowanym ciągiem'
            : ' · Po dopasowanym ciągu'}
      </p>
      {matched ? (
        renderBoard(matched)
      ) : detail ? (
        <AdditionalBoardCrop
          key={detail.sequenceNumber}
          api={api}
          gameId={gameId}
          detail={detail}
        />
      ) : null}
      <div className="boardSearchResultNavigation">
        <button
          className="secondaryButton"
          type="button"
          disabled={loading || index <= minIndex}
          onClick={() => void move(-1)}
        >
          Poprzedni układ
        </button>
        <button
          className="secondaryButton"
          type="button"
          disabled={loading || index >= maxIndex}
          onClick={() => void move(1)}
        >
          Następny układ
        </button>
        <button
          className="secondaryButton"
          type="button"
          ref={openButtonRef}
          aria-label={`Pokaż planszę #${sequenceNumber} z liniami wypłat`}
          onClick={() => {
            if (sequenceNumber !== undefined) onOpenBoard(sequenceNumber);
          }}
        >
          Pokaż planszę
        </button>
      </div>
      {loading ? <p role="status">Wczytywanie zdjęcia…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}

function AdditionalBoardCrop({
  api,
  gameId,
  detail,
}: {
  readonly api: PhotoClient;
  readonly gameId: string;
  readonly detail: BoardSearchModalDetail;
}) {
  const [failed, setFailed] = useState(false);
  return failed ? (
    <p role="alert">
      Zdjęcie planszy #{detail.sequenceNumber} jest niedostępne.
    </p>
  ) : (
    <img
      className="boardSearchBoardAsset"
      alt={`Zdjęcie planszy #${detail.sequenceNumber}`}
      onError={() => setFailed(true)}
      src={api.boardSearchBoardViewUrl(
        gameId,
        detail.sequenceNumber,
        detail.boardChecksumSha256,
        detail.view?.revision,
      )}
    />
  );
}
