'use client';
import { useEffect, useRef, useState } from 'react';
import {
  writePhotoReview,
  type PhotoReviewRequest,
  type Source,
} from '../../../../packages/vision-lab-api-client/src/index';
import { useToast } from '../../../../packages/ui/src/toasts';
import { useAnnotations } from './annotation-context';
import {
  boardStatus,
  photoReviewLabel,
  photoReviewStatus,
  photoVersions,
  sourceAnnotations,
  statusLabel,
} from '../lib/annotation-status';

export function PhotoReviewPanel({
  source,
  geometryDirty,
  geometryLocked,
  geometryStale,
  onProtectionChange,
  onSelect,
}: {
  source: Source;
  geometryDirty: boolean;
  geometryLocked: boolean;
  geometryStale: boolean;
  onProtectionChange: (dirty: boolean, pending: boolean) => void;
  onSelect: (index: number) => void;
}) {
  const { state, accept, refresh } = useAnnotations();
  const notify = useToast();
  const [selected, setSelected] = useState<number[]>([]);
  const [note, setNote] = useState('');
  const [pending, setPending] = useState<PhotoReviewRequest | null>(null);
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const rows = sourceAnnotations(state, source.id);
  const review = state?.photo_reviews?.[source.id];
  const status = photoReviewStatus(rows, review, source.sha256);
  const dirty = !!selected.length || !!note;
  const locked = geometryLocked || busy || pending !== null;
  const acceptedPossible =
    rows.some((row) => boardStatus(row) === 'full') &&
    status.correction === 0 &&
    Object.entries(review?.issues ?? {}).every(
      ([index, issue]) =>
        issue.status === 'needs_review' &&
        rows.some(
          (row) =>
            String(row.board_index) === index &&
            boardStatus(row) === 'full' &&
            row.revision === issue.board_revision,
        ),
    );
  useEffect(() => {
    onProtectionChange(dirty, busy || pending !== null);
  }, [dirty, busy, pending, onProtectionChange]);
  async function submit(action: PhotoReviewRequest['action'], retry = false) {
    if (
      !state ||
      submitting.current ||
      geometryLocked ||
      (!pending && (geometryDirty || geometryStale)) ||
      (pending && !retry)
    )
      return;
    const body = pending ?? {
      request_id: crypto.randomUUID(),
      expected_revision: state.revision,
      actor: 'operator',
      action,
      source_id: source.id,
      source_sha256: source.sha256,
      expected_board_revisions: photoVersions(rows),
      board_indices: action === 'accept' ? [] : selected,
      note: action === 'mark' ? note : '',
    };
    submitting.current = true;
    setBusy(true);
    setPending(body);
    try {
      accept(await writePhotoReview(body));
      setPending(null);
      setSelected([]);
      setNote('');
      notify({
        kind: 'success',
        message:
          body.action === 'accept'
            ? 'Zapisano decyzję przeglądu zdjęcia. Status dotyczy bieżącego zestawu zapisanych geometrii.'
            : body.action === 'mark'
              ? 'Wybrane plansze oznaczono do poprawy. Pozostałe siatki są zachowane.'
              : 'Wycofano oznaczenie. Akceptacja zdjęcia nadal wymaga osobnej decyzji.',
      });
    } catch {
      notify({
        kind: 'error',
        message:
          'Decyzja przeglądu niepotwierdzona. Ponów identyczne żądanie lub odśwież po konflikcie i sprawdź aktualny zestaw.',
      });
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function reconcile() {
    if (submitting.current || geometryLocked) return;
    submitting.current = true;
    setBusy(true);
    try {
      await refresh();
      setPending(null);
      setSelected([]);
      setNote('');
      notify({
        kind: 'info',
        message:
          'Odświeżono przegląd. Sprawdź pozycje i status zdjęcia przed kolejną decyzją.',
      });
    } catch {
      notify({
        kind: 'error',
        message:
          'Nie udało się odczytać przeglądu. Żądanie do ponowienia pozostaje zachowane.',
      });
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return (
    <section
      className="photo-review-panel"
      aria-label="Przegląd całego zdjęcia"
    >
      <h3>Przegląd całego zdjęcia — {photoReviewLabel[status.status]}</h3>
      {review?.rejected && (
        <p>
          Zdjęcie odrzucone w szybkim przeglądzie. Popraw tylko błędne siatki, a
          po sprawdzeniu zaakceptuj całe zdjęcie.
        </p>
      )}
      <p>
        Do poprawy: {status.correction} · Do ponownego sprawdzenia:{' '}
        {status.recheck}. Wybierz numer na zdjęciu, aby obejrzeć zapis i cropy.
        Zaznacz tylko plansze wymagające poprawy.
      </p>
      <fieldset disabled={locked}>
        <div className="review-positions">
          {rows.map((row) => {
            const issue = review?.issues?.[String(row.board_index)];
            return (
              <div key={row.board_index}>
                <label>
                  <input
                    type="checkbox"
                    checked={selected.includes(row.board_index)}
                    onChange={(event) =>
                      setSelected(
                        event.target.checked
                          ? [...selected, row.board_index]
                          : selected.filter(
                              (index) => index !== row.board_index,
                            ),
                      )
                    }
                  />{' '}
                  Pozycja {row.board_index + 1} ·{' '}
                  {statusLabel[boardStatus(row)]}
                  {issue
                    ? ` · ${issue.status === 'needs_correction' ? 'Do poprawy' : 'Do ponownego sprawdzenia'}`
                    : ''}
                </label>
                {issue?.note && <p>Uwaga: {issue.note}</p>}
                <button type="button" onClick={() => onSelect(row.board_index)}>
                  Pokaż pozycję {row.board_index + 1} i cropy
                </button>
              </div>
            );
          })}
        </div>
        <label>
          Uwaga do zaznaczonych plansz (opcjonalna)
          <textarea
            maxLength={1000}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <div className="action-group">
          <button
            disabled={
              !state || !selected.length || geometryDirty || geometryStale
            }
            onClick={() => submit('mark')}
          >
            Oznacz wybrane: Do poprawy
          </button>
          <button
            disabled={
              !state ||
              !selected.length ||
              selected.some((index) => !review?.issues?.[String(index)]) ||
              geometryDirty ||
              geometryStale
            }
            onClick={() => submit('withdraw')}
          >
            Wycofaj błędne oznaczenie
          </button>
          <button
            disabled={
              !state ||
              !acceptedPossible ||
              geometryDirty ||
              geometryStale ||
              dirty
            }
            onClick={() => submit('accept')}
          >
            Akceptuj całe zdjęcie
          </button>
          <button
            disabled={!dirty}
            onClick={() => {
              setSelected([]);
              setNote('');
            }}
          >
            Wyczyść wybór i uwagę
          </button>
        </div>
      </fieldset>
      <p>
        Akceptacja obejmuje zapisane pełne obecne siatki, bez wymagania
        dziewięciu. Po sprawdzeniu poprawionych pełnych siatek jedna akceptacja
        zamyka ich przegląd. Szkic lub sama lokalizacja poprawki nie wystarcza.
        Zapis poprawki pozostawia Cię na tej planszy. Przed decyzją zapisz lub
        odrzuć lokalne zmiany; po konflikcie wczytaj aktualną geometrię.
      </p>
      {pending && (
        <div className="action-group">
          <button
            disabled={busy || geometryLocked}
            onClick={() => submit(pending.action, true)}
          >
            Ponów identyczną decyzję przeglądu
          </button>
          <button disabled={busy || geometryLocked} onClick={reconcile}>
            Odśwież przegląd po konflikcie
          </button>
        </div>
      )}
    </section>
  );
}
