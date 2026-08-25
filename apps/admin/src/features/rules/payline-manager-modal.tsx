'use client';

import type {
  PaylineResponse,
  RulesVersionResponse,
} from '@game-predictor/admin-api-client';
import {
  type FormEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';

import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  archivePayline,
  type PaylinesClient,
  savePayline,
} from '@/features/rules/payline-actions';
import {
  emptyPaylineDraft,
  formatRowPath1Based,
  isPaylineComplete,
  markPaylineArchived,
  type PaylineDraft,
  paylineToDraft,
  selectPaylineCell,
  upsertPayline,
  validatePaylineDraft,
} from '@/features/rules/payline-editor-state';

type LoadState = 'loading' | 'ready' | 'error';
type EditorState =
  | { readonly mode: 'closed' }
  | { readonly mode: 'create' }
  | { readonly mode: 'edit'; readonly payline: PaylineResponse };

interface PaylineManagerModalProps {
  readonly api: PaylinesClient;
  readonly onClose: () => void;
  readonly rulesVersion: RulesVersionResponse;
}

export function PaylineManagerModal({
  api,
  onClose,
  rulesVersion,
}: PaylineManagerModalProps) {
  const [paylines, setPaylines] = useState<readonly PaylineResponse[]>([]);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [loadError, setLoadError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [editor, setEditor] = useState<EditorState>({ mode: 'closed' });
  const [draft, setDraft] = useState<PaylineDraft>(() =>
    emptyPaylineDraft(rulesVersion.columns),
  );
  const [formError, setFormError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [archiveCandidateId, setArchiveCandidateId] = useState<string | null>(
    null,
  );
  const [archivingId, setArchivingId] = useState<string | null>(null);
  const loadRequestId = useRef(0);
  const mutationInProgress = useRef(false);
  const canMutate = rulesVersion.status === 'draft';

  const loadPaylines = useCallback(async () => {
    const requestId = ++loadRequestId.current;
    setLoadState('loading');
    setLoadError('');
    try {
      const result = await api.listPaylines(rulesVersion.id);
      if (requestId !== loadRequestId.current) return;
      if (result.error !== undefined || result.data === undefined) {
        setLoadError(
          apiErrorMessage(result.error, 'Nie udało się pobrać wzorców.'),
        );
        setLoadState('error');
        return;
      }
      setPaylines(result.data);
      setLoadState('ready');
    } catch {
      if (requestId === loadRequestId.current) {
        setLoadError('Brak połączenia z lokalnym Admin API.');
        setLoadState('error');
      }
    }
  }, [api, rulesVersion.id]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void loadPaylines();
    });
    return () => {
      cancelled = true;
      loadRequestId.current += 1;
    };
  }, [loadPaylines]);

  function openCreate() {
    setDraft(emptyPaylineDraft(rulesVersion.columns));
    setFormError('');
    setFeedback('');
    setArchiveCandidateId(null);
    setEditor({ mode: 'create' });
  }

  function openEdit(payline: PaylineResponse) {
    setDraft(paylineToDraft(payline));
    setFormError('');
    setFeedback('');
    setArchiveCandidateId(null);
    setEditor({ mode: 'edit', payline });
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutationInProgress.current || editor.mode === 'closed' || !canMutate) {
      return;
    }
    const validation = validatePaylineDraft(draft, {
      columns: rulesVersion.columns,
      rows: rulesVersion.rows,
    });
    if (!validation.valid) {
      setFormError(validation.error);
      return;
    }
    mutationInProgress.current = true;
    setIsSubmitting(true);
    setFormError('');
    const result = await savePayline(
      api,
      rulesVersion.id,
      editor.mode === 'create'
        ? { mode: 'create' }
        : { mode: 'edit', paylineId: editor.payline.id },
      validation.value,
      paylines,
    );
    mutationInProgress.current = false;
    setIsSubmitting(false);
    if (!result.ok) {
      setFormError(result.error);
      return;
    }
    setPaylines((current) => upsertPayline(current, result.payline));
    setEditor({ mode: 'closed' });
    setFeedback(
      editor.mode === 'create'
        ? `Dodano wzór „${result.payline.code}”.`
        : `Zapisano wzór „${result.payline.code}”.`,
    );
  }

  async function confirmArchive(payline: PaylineResponse) {
    if (mutationInProgress.current || !canMutate) return;
    mutationInProgress.current = true;
    setArchivingId(payline.id);
    setLoadError('');
    const result = await archivePayline(api, rulesVersion.id, payline.id);
    mutationInProgress.current = false;
    setArchivingId(null);
    if (!result.ok) {
      setLoadError(result.error);
      return;
    }
    setPaylines((current) => markPaylineArchived(current, payline.id));
    setArchiveCandidateId(null);
    setFeedback(`Zarchiwizowano wzór „${payline.code}”.`);
  }

  return (
    <dialog
      aria-labelledby="payline-manager-title"
      aria-modal="true"
      className="paylineDialog"
      open
    >
      <div className="paylineDialogCard">
        <header className="paylineDialogHeader">
          <div>
            <p className="eyebrow">
              Wersja {rulesVersion.version} · {rulesVersion.rows} ×{' '}
              {rulesVersion.columns}
            </p>
            <h2 id="payline-manager-title">
              {editor.mode === 'closed'
                ? 'Wzorce wypłat'
                : editor.mode === 'create'
                  ? 'Dodaj wzór'
                  : `Edytuj „${editor.payline.code}”`}
            </h2>
          </div>
          <button
            aria-label="Zamknij modal wzorców"
            className="iconButton"
            disabled={isSubmitting || archivingId !== null}
            onClick={onClose}
            type="button"
          >
            ×
          </button>
        </header>

        {editor.mode === 'closed' ? (
          <>
            <div className="paylineToolbar">
              <p>
                Wiersze są pokazane od 1. Każda pozycja tablicy odpowiada jednej
                kolumnie.
              </p>
              {canMutate ? (
                <button
                  className="primaryButton"
                  onClick={openCreate}
                  type="button"
                >
                  + Dodaj wzór
                </button>
              ) : (
                <span className="immutableLabel">Wersja tylko do odczytu</span>
              )}
            </div>
            {feedback ? <p className="feedbackBanner">{feedback}</p> : null}
            {loadError && loadState !== 'error' ? (
              <p className="feedbackBanner feedbackBannerError" role="alert">
                {loadError}
              </p>
            ) : null}

            {loadState === 'loading' ? (
              <ModalState
                text="Pobieram zapisane wzorce…"
                title="Wczytywanie"
              />
            ) : loadState === 'error' ? (
              <ModalState
                error
                onRetry={() => void loadPaylines()}
                text={loadError}
                title="Nie udało się pobrać wzorców"
              />
            ) : paylines.length === 0 ? (
              <ModalState
                onRetry={canMutate ? openCreate : undefined}
                text="Ta wersja reguł nie zawiera jeszcze żadnej payline."
                title="Brak wzorców"
              />
            ) : (
              <div className="paylineTable" role="table">
                <div className="paylineTableHeader" role="row">
                  <span role="columnheader">Wzorzec</span>
                  <span role="columnheader">Ścieżka wierszy</span>
                  <span role="columnheader">Akcje</span>
                </div>
                {paylines.map((payline) => (
                  <div className="paylineTableRow" key={payline.id} role="row">
                    <div role="cell">
                      <strong>{payline.code}</strong>
                      <span
                        className={`paylineStatus ${
                          payline.isActive ? 'paylineStatusActive' : ''
                        }`}
                      >
                        {payline.isActive ? 'Aktywny' : 'Zarchiwizowany'}
                      </span>
                    </div>
                    <code className="rowPathValue" role="cell">
                      {formatRowPath1Based(payline.rowPath)}
                    </code>
                    <div className="rowActions" role="cell">
                      {archiveCandidateId === payline.id ? (
                        <>
                          <button
                            className="textButton"
                            disabled={archivingId === payline.id}
                            onClick={() => setArchiveCandidateId(null)}
                            type="button"
                          >
                            Anuluj
                          </button>
                          <button
                            className="dangerButton"
                            disabled={archivingId === payline.id}
                            onClick={() => void confirmArchive(payline)}
                            type="button"
                          >
                            {archivingId === payline.id
                              ? 'Archiwizowanie…'
                              : 'Potwierdź'}
                          </button>
                        </>
                      ) : canMutate ? (
                        <>
                          <button
                            className="secondaryButton"
                            onClick={() => openEdit(payline)}
                            type="button"
                          >
                            Edytuj
                          </button>
                          {payline.isActive ? (
                            <button
                              className="textButton"
                              onClick={() => setArchiveCandidateId(payline.id)}
                              type="button"
                            >
                              Archiwizuj
                            </button>
                          ) : null}
                        </>
                      ) : (
                        <span className="immutableLabel">Odczyt</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <form className="paylineEditorForm" onSubmit={onSubmit}>
            <div className="paylineFields">
              <label>
                Kod stabilny
                <input
                  disabled={editor.mode === 'edit'}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      code: event.target.value,
                    }))
                  }
                  value={draft.code}
                />
              </label>
              <label className="checkboxField">
                <input
                  checked={draft.isActive}
                  onChange={(event) =>
                    setDraft((current) => ({
                      ...current,
                      isActive: event.target.checked,
                    }))
                  }
                  type="checkbox"
                />
                Aktywny wzorzec
              </label>
            </div>

            <div className="paylineGridSection">
              <div>
                <h3>Wybierz przebieg linii</h3>
                <p>
                  Kliknięcie innego kafelka w tej samej kolumnie zastępuje
                  poprzedni wybór.
                </p>
              </div>
              <div
                className="paylineGrid"
                style={{
                  gridTemplateColumns: `repeat(${rulesVersion.columns}, minmax(62px, 1fr))`,
                }}
              >
                {Array.from(
                  {
                    length: rulesVersion.rows * rulesVersion.columns,
                  },
                  (_, index) => {
                    const row = Math.floor(index / rulesVersion.columns);
                    const column = index % rulesVersion.columns;
                    const selected = draft.rowPath[column] === row;
                    return (
                      <button
                        aria-label={`Kolumna ${column + 1}, wiersz ${row + 1}`}
                        aria-pressed={selected}
                        className={`paylineCell ${
                          selected ? 'paylineCellSelected' : ''
                        }`}
                        key={`${column}-${row}`}
                        onClick={() =>
                          setDraft((current) => ({
                            ...current,
                            rowPath: selectPaylineCell(
                              current.rowPath,
                              column,
                              row,
                            ),
                          }))
                        }
                        type="button"
                      >
                        <span>W{row + 1}</span>
                        <small>K{column + 1}</small>
                      </button>
                    );
                  },
                )}
              </div>
              <p className="selectedPath">
                Wybrana ścieżka:{' '}
                <code>
                  [
                  {draft.rowPath
                    .map((row) => (row === null ? '—' : String(row + 1)))
                    .join(', ')}
                  ]
                </code>
              </p>
            </div>

            {formError ? (
              <p className="formError" role="alert">
                {formError}
              </p>
            ) : null}
            <div className="formActions">
              <button
                className="textButton"
                disabled={isSubmitting}
                onClick={() => setEditor({ mode: 'closed' })}
                type="button"
              >
                Wróć do tabeli
              </button>
              <button
                className="primaryButton"
                disabled={
                  isSubmitting ||
                  !isPaylineComplete(draft.rowPath, rulesVersion.columns)
                }
                type="submit"
              >
                {isSubmitting ? 'Zapisywanie…' : 'Zapisz wzór'}
              </button>
            </div>
          </form>
        )}
      </div>
    </dialog>
  );
}

function ModalState({
  error = false,
  onRetry,
  text,
  title,
}: {
  readonly error?: boolean;
  readonly onRetry?: () => void;
  readonly text: string;
  readonly title: string;
}) {
  return (
    <div className={`modalState ${error ? 'statePanelError' : ''}`}>
      <span
        className={title === 'Wczytywanie' ? 'loadingMark' : 'stateIcon'}
        aria-hidden="true"
      >
        {title === 'Wczytywanie' ? '' : error ? '!' : '0'}
      </span>
      <div>
        <h3>{title}</h3>
        <p>{text}</p>
        {onRetry ? (
          <button className="secondaryButton" onClick={onRetry} type="button">
            {error ? 'Spróbuj ponownie' : 'Dodaj wzór'}
          </button>
        ) : null}
      </div>
    </div>
  );
}
