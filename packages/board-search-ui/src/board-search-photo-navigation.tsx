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
  const [extra, setExtra] = useState<readonly BoardSearchModalDetail[]>([]);
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
  const detail = extra[index - boards.length];
  const sequenceNumber = matched?.sequenceNumber ?? detail?.sequenceNumber;
  const total = boards.length + 10;

  async function next() {
    if (pending.current || index >= total - 1) return;
    setError(null);
    if (index + 1 < boards.length + extra.length) {
      setIndex(index + 1);
      return;
    }
    const requested =
      boards[boards.length - 1].sequenceNumber + extra.length + 1;
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
      setExtra((previous) => [...previous, data]);
      setIndex(index + 1);
    } catch (cause: unknown) {
      if (active.current)
        setError(
          `${cause instanceof Error ? cause.message : apiErrorMessage(cause, `Nie udało się wczytać planszy #${requested}.`)} Poprzednie zdjęcie pozostaje widoczne. Kliknij „Następny układ”, aby ponowić.`,
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
        Zdjęcie #{sequenceNumber} · {index + 1} z {total}
        {matched
          ? ` · Układ ${index + 1} dopasowania · ${matched.score.score.toFixed(1)}%`
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
          disabled={loading || index === 0}
          onClick={() => {
            setError(null);
            setIndex(index - 1);
          }}
        >
          Poprzedni układ
        </button>
        <button
          className="secondaryButton"
          type="button"
          disabled={loading || index >= total - 1}
          onClick={() => void next()}
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
      {loading ? <p role="status">Wczytywanie następnego zdjęcia…</p> : null}
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
