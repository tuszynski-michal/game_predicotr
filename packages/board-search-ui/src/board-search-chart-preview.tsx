'use client';

/* Images are served through the current Admin/share data source. */
/* eslint-disable @next/next/no-img-element */

import { useEffect, useState } from 'react';
import { apiErrorMessage } from './api-error';
import type {
  BoardSearchDataSource,
  BoardSearchModalDetail,
} from './board-search-data-source';

type PreviewClient = Pick<
  BoardSearchDataSource,
  'getBoardSearchBoardDetail' | 'boardSearchBoardViewUrl'
>;

type PreviewState =
  | { kind: 'loading' }
  | { kind: 'error'; message: string }
  | { kind: 'ready'; detail: BoardSearchModalDetail };

/** Mounted with the calculation and row identity as its key. */
export function BoardSearchChartPreview({
  client,
  gameId,
  sequenceNumber,
  spinNumber,
  onClose,
}: {
  readonly client: PreviewClient;
  readonly gameId: string;
  readonly sequenceNumber: number;
  readonly spinNumber: number;
  readonly onClose: () => void;
}) {
  const [state, setState] = useState<PreviewState>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);
  const [imageFailed, setImageFailed] = useState(false);
  const readDetail = client.getBoardSearchBoardDetail;
  useEffect(() => {
    let cancelled = false;
    void readDetail(gameId, sequenceNumber)
      .then((response) => {
        if (cancelled) return;
        if (response.error !== undefined || response.data === undefined) {
          setState({
            kind: 'error',
            message: apiErrorMessage(
              response.error,
              'Nie udało się pobrać podglądu planszy.',
            ),
          });
        } else if (
          response.data.gameId !== gameId ||
          response.data.sequenceNumber !== sequenceNumber
        ) {
          setState({
            kind: 'error',
            message: 'Podgląd dotyczy innej planszy. Spróbuj ponownie.',
          });
        } else {
          setState({ kind: 'ready', detail: response.data });
        }
      })
      .catch(() => {
        if (!cancelled)
          setState({
            kind: 'error',
            message:
              'Nie udało się połączyć podczas pobierania podglądu planszy.',
          });
      });
    return () => {
      cancelled = true;
    };
  }, [readDetail, gameId, sequenceNumber, attempt]);
  const detail = state.kind === 'ready' ? state.detail : null;
  const imageUrl =
    detail?.view && !detail.documentStale
      ? client.boardSearchBoardViewUrl(
          gameId,
          sequenceNumber,
          detail.boardChecksumSha256,
          detail.view.revision,
        )
      : null;
  return (
    <aside
      className="boardSearchChartPreview"
      aria-label={`Podgląd planszy ${sequenceNumber}`}
    >
      <div className="boardSearchChartPreviewHeading">
        <strong>
          Plansza #{sequenceNumber.toLocaleString('pl-PL')} · spin{' '}
          {spinNumber.toLocaleString('pl-PL')}
        </strong>
        <button
          type="button"
          className="textButton"
          onClick={onClose}
          aria-label="Zamknij podgląd planszy"
        >
          Zamknij
        </button>
      </div>
      {state.kind === 'loading' ? (
        <p role="status">Wczytywanie planszy…</p>
      ) : null}
      {state.kind === 'error' ? <p role="alert">{state.message}</p> : null}
      {detail !== null && (imageUrl === null || imageFailed) ? (
        <p role="status">
          {detail.documentStale
            ? 'Zdjęcie planszy zmieniło się. Odśwież wynik przed podglądem.'
            : 'Zdjęcie planszy jest niedostępne.'}
        </p>
      ) : null}
      {imageUrl !== null && !imageFailed ? (
        <img
          src={imageUrl}
          alt={`Plansza ${sequenceNumber} — spin ${spinNumber}`}
          onError={() => setImageFailed(true)}
        />
      ) : null}
      {state.kind === 'error' || imageFailed ? (
        <button
          type="button"
          className="secondaryButton"
          onClick={() => {
            setState({ kind: 'loading' });
            setImageFailed(false);
            setAttempt((value) => value + 1);
          }}
        >
          Ponów podgląd
        </button>
      ) : null}
    </aside>
  );
}
