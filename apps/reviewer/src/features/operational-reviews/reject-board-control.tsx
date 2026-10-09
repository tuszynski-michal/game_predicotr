'use client';

import { type KeyboardEvent, useEffect, useId, useRef, useState } from 'react';

import {
  BOARD_REJECTION_REASONS,
  MAX_BOARD_REJECTION_NOTE_LENGTH,
  boardRejectionDraftError,
  type BoardRejectionReason,
  type BoardRejectionRequest,
} from './board-rejection-state.ts';
import type { MutationOutcome } from './mutation-outcome.ts';

/**
 * "Odrzuć planszę" (TASK-0949, W7): a button, a reason picker and a
 * confirmation. The dialog owns one idempotency key per opening. A definite
 * answer (applied or refused) closes it and hands the result to the owner;
 * an unknown outcome (lost connection, 5xx, timeout) keeps the dialog, the
 * key and the frozen draft so the retry replays exactly the same request.
 */
export function RejectBoardControl<T>({
  confirmLabel = 'Potwierdź odrzucenie',
  consequences,
  disabled = false,
  label = 'Odrzuć planszę',
  onDone,
  onRefused,
  subject,
  submit,
}: {
  readonly confirmLabel?: string;
  /** Plain-language effects shown before the confirmation. */
  readonly consequences: readonly string[];
  readonly disabled?: boolean;
  readonly label?: string;
  readonly onDone: (data: T) => void | Promise<void>;
  /** The server answered 4xx: nothing changed; ``code`` is the API error code. */
  readonly onRefused: (
    message: string,
    code: string | null,
  ) => void | Promise<void>;
  /** What is rejected, e.g. "sekwencja 100, pozycja 3". */
  readonly subject: string;
  readonly submit: (
    request: BoardRejectionRequest,
  ) => Promise<MutationOutcome<T>>;
}) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  async function handleSubmit(
    request: BoardRejectionRequest,
  ): Promise<string | null> {
    const outcome = await submit(request);
    if (!mounted.current) return null;
    if (outcome.kind === 'unknown') return outcome.message;
    setOpen(false);
    if (outcome.kind === 'done') await onDone(outcome.data);
    else await onRefused(outcome.message, outcome.code);
    return null;
  }

  return (
    <>
      <button
        className="dangerButton"
        disabled={disabled}
        onClick={() => setOpen(true)}
        ref={opener}
        type="button"
      >
        {label}
      </button>
      {open ? (
        <RejectBoardDialog
          confirmLabel={confirmLabel}
          consequences={consequences}
          onCancel={() => setOpen(false)}
          onSubmit={handleSubmit}
          opener={opener}
          subject={subject}
        />
      ) : null}
    </>
  );
}

function RejectBoardDialog({
  confirmLabel,
  consequences,
  onCancel,
  onSubmit,
  opener,
  subject,
}: {
  readonly confirmLabel: string;
  readonly consequences: readonly string[];
  readonly onCancel: () => void;
  readonly onSubmit: (request: BoardRejectionRequest) => Promise<string | null>;
  readonly opener: { readonly current: HTMLElement | null };
  readonly subject: string;
}) {
  const titleId = useId();
  // Fixed for this opening: a retry after a lost response replays it.
  const [idempotencyKey] = useState(() => crypto.randomUUID());
  const [reason, setReason] = useState<BoardRejectionReason | null>(null);
  const [note, setNote] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [unknownOutcome, setUnknownOutcome] = useState('');
  const submittingRef = useRef(false);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const draftError = boardRejectionDraftError(reason, note);

  // Focus enters the dialog on open and returns to the opener on close.
  useEffect(() => {
    const returnTo = opener.current;
    dialogRef.current?.focus();
    return () => {
      if (returnTo?.isConnected) returnTo.focus();
    };
  }, [opener]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    // Keep the editors' window-level symbol shortcuts out of the dialog.
    event.stopPropagation();
    if (event.key === 'Escape') {
      if (!submittingRef.current) onCancel();
      return;
    }
    if (event.key !== 'Tab') return;
    const dialog = dialogRef.current;
    if (dialog === null) return;
    const focusable = [
      ...dialog.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), textarea:not(:disabled)',
      ),
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

  async function confirm() {
    if (submittingRef.current || reason === null || draftError !== '') return;
    submittingRef.current = true;
    setSubmitting(true);
    const failure = await onSubmit({ idempotencyKey, note, reason });
    submittingRef.current = false;
    // On a definite answer the owner has already closed (unmounted) us.
    setSubmitting(false);
    if (failure !== null) setUnknownOutcome(failure);
  }

  // After an unknown outcome the draft is frozen so the retry is identical.
  const frozen = unknownOutcome !== '';
  return (
    <div
      aria-labelledby={titleId}
      aria-modal="true"
      className="operationalReviewDialogBackdrop"
      role="dialog"
    >
      <div
        className="operationalReviewConfirmDialog"
        onKeyDown={handleKeyDown}
        ref={dialogRef}
        tabIndex={-1}
      >
        <p className="eyebrow">Odrzucenie planszy</p>
        <h2 id={titleId}>Odrzucić planszę ({subject})?</h2>
        <fieldset
          className="boardRejectionReasons"
          disabled={submitting || frozen}
        >
          <legend>Powód</legend>
          {BOARD_REJECTION_REASONS.map((entry) => (
            <label key={entry.value}>
              <input
                checked={reason === entry.value}
                name="board-rejection-reason"
                onChange={() => setReason(entry.value)}
                type="radio"
                value={entry.value}
              />
              {entry.label}
            </label>
          ))}
          {reason === 'other' ? (
            <label className="boardRejectionNote">
              Opis powodu
              <textarea
                maxLength={MAX_BOARD_REJECTION_NOTE_LENGTH}
                onChange={(event) => setNote(event.target.value)}
                rows={3}
                value={note}
              />
            </label>
          ) : null}
        </fieldset>
        <ul className="geometryCorrectionPreview">
          {consequences.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
        {reason !== null && draftError !== '' ? (
          <p role="alert">{draftError}</p>
        ) : null}
        {unknownOutcome ? <p role="alert">{unknownOutcome}</p> : null}
        <div className="buttonRow">
          <button
            className="secondaryButton"
            disabled={submitting}
            onClick={onCancel}
            type="button"
          >
            Anuluj
          </button>
          <button
            className="dangerButton"
            disabled={submitting || reason === null || draftError !== ''}
            onClick={() => void confirm()}
            type="button"
          >
            {submitting
              ? 'Odrzucanie…'
              : frozen
                ? 'Spróbuj ponownie'
                : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
