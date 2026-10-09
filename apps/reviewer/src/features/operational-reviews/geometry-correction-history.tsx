'use client';

import type {
  AdminApiClient,
  GeometryCorrectionResponse,
  GeometryCorrectionRevertPreviewResponse,
} from '@game-predictor/admin-api-client';
import {
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

import { apiErrorMessage } from '../catalog/catalog-api-error';

export type GeometryCorrectionHistoryClient = Pick<
  AdminApiClient,
  | 'listGeometryCorrections'
  | 'previewGeometryCorrectionRevert'
  | 'revertGeometryCorrection'
>;

type ListState = 'error' | 'loading' | 'ready';

interface PendingRevert {
  /** Fixed for the whole modal opening: every retry replays the same key. */
  readonly idempotencyKey: string;
  readonly correction: GeometryCorrectionResponse;
  readonly preview: GeometryCorrectionRevertPreviewResponse | null;
  readonly previewError: string;
}

const LOST_CONNECTION = 'Połączenie z lokalnym Admin API zostało przerwane.';

/**
 * "Ostatnie korekty" (TASK-0948): the latest manual geometry saves of the
 * import with a guarded revert. The revert is offered only for rows the API
 * marks `revertable`; the confirmation shows the preview of its effects and
 * sends the CAS tokens of that preview with a fresh idempotency key.
 */
export function GeometryCorrectionHistory({
  api,
  gameId,
  importJobId,
  onReverted,
  refreshToken,
}: {
  readonly api: GeometryCorrectionHistoryClient;
  readonly gameId: string;
  readonly importJobId: string;
  /** Called after a successful revert so the owner can reload its queue. */
  readonly onReverted: () => void | Promise<void>;
  /** Changing the value reloads the list (e.g. after a saved correction). */
  readonly refreshToken: number;
}) {
  const [items, setItems] = useState<readonly GeometryCorrectionResponse[]>([]);
  const [state, setState] = useState<ListState>('loading');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState<PendingRevert | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [dialogError, setDialogError] = useState('');
  const mounted = useRef(true);
  const requestId = useRef(0);
  const submittingRef = useRef(false);
  // The opening whose preview may still land, and the openings that already
  // sent a revert (their CAS tokens and body are frozen).
  const openingRef = useRef<string | null>(null);
  const sentKeysRef = useRef<Set<string>>(new Set());
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const dialogOpen = pending !== null;

  const load = useCallback(async () => {
    const current = ++requestId.current;
    let result;
    try {
      result = await api.listGeometryCorrections({ gameId, importJobId });
    } catch {
      result = null;
    }
    if (!mounted.current || current !== requestId.current) return;
    if (result === null) {
      setState('error');
      setError(LOST_CONNECTION);
      return;
    }
    if (result.error !== undefined || result.data === undefined) {
      setState('error');
      setError(
        apiErrorMessage(result.error, 'Nie udało się pobrać ostatnich korekt.'),
      );
      return;
    }
    setItems(result.data.items);
    setError('');
    setState('ready');
  }, [api, gameId, importJobId]);

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void load());
    return () => {
      mounted.current = false;
    };
  }, [load, refreshToken]);

  // Focus moves into the modal on open and returns to the opener on close.
  useEffect(() => {
    if (!dialogOpen) return;
    const opener =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    dialogRef.current?.focus();
    return () => {
      if (opener?.isConnected) opener.focus();
    };
  }, [dialogOpen]);

  function handleDialogKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    // Keep the editor's window-level symbol shortcuts out of the modal.
    event.stopPropagation();
    if (event.key === 'Escape') {
      if (!submittingRef.current) setPending(null);
      return;
    }
    if (event.key !== 'Tab') return;
    const dialog = dialogRef.current;
    if (dialog === null) return;
    const focusable = [
      ...dialog.querySelectorAll<HTMLElement>('button:not(:disabled)'),
    ];
    if (focusable.length === 0) {
      event.preventDefault();
      dialog.focus();
      return;
    }
    const first = focusable[0]!;
    const last = focusable[focusable.length - 1]!;
    const active = document.activeElement;
    if (event.shiftKey && (active === first || active === dialog)) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function openRevert(correction: GeometryCorrectionResponse) {
    setNotice('');
    setDialogError('');
    // Each opening owns its key; responses are matched to it, not to the
    // correction, so a late response of a closed opening is ignored.
    const openingKey = crypto.randomUUID();
    openingRef.current = openingKey;
    setPending({
      correction,
      idempotencyKey: openingKey,
      preview: null,
      previewError: '',
    });
    let result;
    try {
      result = await api.previewGeometryCorrectionRevert(
        correction.boardGeometryRevisionId,
        { gameId, importJobId },
      );
    } catch {
      result = null;
    }
    if (!mounted.current) return;
    if (
      openingRef.current !== openingKey ||
      sentKeysRef.current.has(openingKey)
    )
      return;
    const failure =
      result === null
        ? LOST_CONNECTION
        : result.error !== undefined || result.data === undefined
          ? apiErrorMessage(
              result.error,
              'Nie udało się pobrać podglądu cofnięcia.',
            )
          : '';
    setPending((current) =>
      current?.idempotencyKey !== openingKey
        ? current
        : {
            ...current,
            preview: result?.data ?? null,
            previewError: failure,
          },
    );
    // A blocked preview means the list is stale: show the fresh state.
    if (failure) void load();
  }

  async function confirmRevert() {
    if (pending === null || pending.preview === null) return;
    if (submittingRef.current) return;
    submittingRef.current = true;
    setSubmitting(true);
    setDialogError('');
    const { correction, preview } = pending;
    sentKeysRef.current.add(pending.idempotencyKey);
    let result;
    try {
      // The key and the CAS tokens are fixed per modal opening, so a retry
      // after a lost response replays the same request and the server can
      // answer it idempotently instead of reverting twice.
      result = await api.revertGeometryCorrection(
        correction.boardGeometryRevisionId,
        { gameId, importJobId },
        {
          expectedGeometryRevision: preview.expectedGeometryRevision,
          expectedResolutionRevision: preview.expectedResolutionRevision,
          idempotencyKey: pending.idempotencyKey,
        },
      );
    } catch {
      result = null;
    }
    submittingRef.current = false;
    if (!mounted.current) return;
    setSubmitting(false);
    const succeeded =
      result !== null &&
      result.error === undefined &&
      result.data !== undefined;
    if (!succeeded && !isDefiniteRefusal(result)) {
      // Unknown outcome (thrown fetch, no response, unparseable body, 5xx):
      // the server may have committed, so keep the modal, the key and the
      // body, and let the operator replay the same request.
      setDialogError(`${LOST_CONNECTION} Wynik cofnięcia jest nieznany.`);
      return;
    }
    setPending(null);
    openingRef.current = null;
    if (!succeeded) {
      setNotice(
        apiErrorMessage(result?.error, 'Nie udało się cofnąć korekty.'),
      );
    } else {
      // `created: false` is a replayed success and is handled the same way.
      setNotice(
        'Korekta została cofnięta. Kolejka i lista zostały odświeżone.',
      );
    }
    await Promise.all([load(), onReverted()]);
  }

  return (
    <section
      aria-label="Ostatnie korekty"
      className="geometryCorrectionHistory"
    >
      <header className="geometryCorrectionHistoryHeader">
        <h3>Ostatnie korekty</h3>
        <button
          className="secondaryButton"
          onClick={() => void load()}
          type="button"
        >
          Odśwież
        </button>
      </header>
      {notice ? (
        <p className="operationalReviewNotice" role="status">
          {notice}
        </p>
      ) : null}
      {state === 'loading' ? <p>Pobieram ostatnie korekty.</p> : null}
      {state === 'error' ? (
        <p className="errorState" role="alert">
          {error}
        </p>
      ) : null}
      {state === 'ready' && items.length === 0 ? (
        <p>Ten import nie ma jeszcze zapisanych korekt.</p>
      ) : null}
      {items.length > 0 ? (
        <ul className="geometryCorrectionHistoryList">
          {items.map((item) => (
            <li
              className="geometryCorrectionHistoryRow"
              key={item.boardGeometryRevisionId}
            >
              <span>{formatLocalTime(item.createdAt)}</span>
              <span>Sekwencja {item.sequenceNumber}</span>
              <span>Pozycja {item.positionIndex}</span>
              <span>{kindLabel(item.kind)}</span>
              <span>{item.actor}</span>
              {item.revertable ? (
                <button
                  className="secondaryButton"
                  onClick={() => void openRevert(item)}
                  type="button"
                >
                  Cofnij
                </button>
              ) : (
                <span className="geometryCorrectionHistoryBlocked">
                  {item.blockingReasonMessage ??
                    'Tej korekty nie można cofnąć.'}
                </span>
              )}
            </li>
          ))}
        </ul>
      ) : null}
      {pending ? (
        <div
          aria-labelledby="geometry-revert-title"
          aria-modal="true"
          className="operationalReviewDialogBackdrop"
          role="dialog"
        >
          <div
            className="operationalReviewConfirmDialog"
            onKeyDown={handleDialogKeyDown}
            ref={dialogRef}
            tabIndex={-1}
          >
            <p className="eyebrow">Cofnięcie korekty</p>
            <h2 id="geometry-revert-title">
              Cofnąć korektę sekwencji {pending.correction.sequenceNumber},
              pozycja {pending.correction.positionIndex}?
            </h2>
            {pending.previewError ? (
              <p role="alert">{pending.previewError}</p>
            ) : pending.preview === null ? (
              <p>Pobieram podgląd skutków.</p>
            ) : (
              <PreviewSummary preview={pending.preview} />
            )}
            {dialogError ? <p role="alert">{dialogError}</p> : null}
            <div className="buttonRow">
              <button
                className="secondaryButton"
                disabled={submitting}
                onClick={() => setPending(null)}
                type="button"
              >
                Anuluj
              </button>
              <button
                className="primaryButton"
                disabled={
                  submitting ||
                  pending.preview === null ||
                  pending.previewError !== ''
                }
                onClick={() => void confirmRevert()}
                type="button"
              >
                {submitting
                  ? 'Cofanie…'
                  : dialogError
                    ? 'Spróbuj ponownie'
                    : 'Potwierdź cofnięcie'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}

/**
 * The generated client never throws on transport errors: it returns
 * `{error, response}` with `response` undefined. Only a 4xx response carrying
 * an API error `code` is a definite refusal; a 5xx may follow a commit, so it
 * stays an unknown outcome and the idempotent retry resolves it.
 */
function isDefiniteRefusal(
  result: {
    readonly error?: unknown;
    readonly response?: { readonly status: number };
  } | null,
): boolean {
  if (result === null || result.response === undefined) return false;
  const { status } = result.response;
  if (status < 400 || status >= 500) return false;
  const error = result.error;
  return (
    typeof error === 'object' &&
    error !== null &&
    'code' in error &&
    typeof error.code === 'string'
  );
}

function PreviewSummary({
  preview,
}: {
  readonly preview: GeometryCorrectionRevertPreviewResponse;
}) {
  return (
    <ul className="geometryCorrectionPreview">
      <li>
        {preview.removesBoard
          ? 'Plansza zostanie usunięta, a slot wróci do kolejki korekty.'
          : 'Plansza wróci do poprzedniej geometrii.'}
      </li>
      <li>Usuwane komórki: {preview.removedCellCount}</li>
      <li>Przywracane decyzje komórek: {preview.restoredCellDecisionCount}</li>
      <li>Przepinane sąsiednie plansze: {preview.repointedBoardCount}</li>
      {preview.restoredSourceEngineKind ? (
        <li>
          Przywracane źródło: {preview.restoredSourceEngineKind}
          {preview.restoredSourceStatus
            ? ` (${preview.restoredSourceStatus})`
            : ''}
        </li>
      ) : null}
    </ul>
  );
}

function kindLabel(kind: GeometryCorrectionResponse['kind']): string {
  return kind === 'pending_slot' ? 'slot' : 'plansza';
}

function formatLocalTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString('pl-PL', { dateStyle: 'short', timeStyle: 'medium' });
}
