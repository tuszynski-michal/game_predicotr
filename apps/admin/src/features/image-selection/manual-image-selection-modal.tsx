'use client';

import type {
  ImageSelectionGroupResponse,
  ImageSelectionManualApprovalResponse,
} from '@game-predictor/admin-api-client';
import {
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { apiErrorMessage } from '../catalog/catalog-api-error';
import type { ImageSelectionClient } from './image-selection-actions';

interface ManualImageSelectionModalProps {
  readonly apiBaseUrl: string;
  readonly client: ImageSelectionClient;
  readonly groups: readonly ImageSelectionGroupResponse[];
  readonly onClose: () => void;
  readonly onGroupUpdated: (group: ImageSelectionGroupResponse) => void;
  readonly runId: string;
}

interface ManualDraft {
  readonly candidateId: string | null;
  readonly fileName: string;
  readonly idempotencyKey: string | null;
  readonly previewUrl: string;
  readonly rangeEnd: string;
  readonly rangeStart: string;
}

export function ManualImageSelectionModal({
  apiBaseUrl,
  client,
  groups,
  onClose,
  onGroupUpdated,
  runId,
}: ManualImageSelectionModalProps) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const approvalInFlightRef = useRef(false);
  const objectUrlsRef = useRef(new Set<string>());
  const [index, setIndex] = useState(() => firstPendingIndex(groups));
  const [drafts, setDrafts] = useState<Record<string, ManualDraft>>(() =>
    buildInitialDrafts(apiBaseUrl, runId, groups),
  );
  const [uploading, setUploading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState('');
  const current = groups[index];
  const currentDraft = current === undefined ? undefined : drafts[current.id];
  const approvedCount = useMemo(
    () =>
      groups.filter(
        (group) =>
          group.status === 'manually_selected' ||
          group.status === 'missing_image',
      ).length,
    [groups],
  );

  useEffect(() => {
    const objectUrls = objectUrlsRef.current;
    dialogRef.current?.focus();
    return () => {
      for (const url of objectUrls) URL.revokeObjectURL(url);
      objectUrls.clear();
    };
  }, []);

  function navigate(offset: number) {
    if (groups.length < 2 || uploading || approving) return;
    setError('');
    setIndex((value) => (value + offset + groups.length) % groups.length);
  }

  function updateDraft(groupId: string, patch: Partial<ManualDraft>) {
    setDrafts((value) => {
      const existing = value[groupId];
      if (existing === undefined) return value;
      return { ...value, [groupId]: { ...existing, ...patch } };
    });
  }

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = '';
    if (current === undefined || file === undefined) return;
    if (
      !/\.jpe?g$/i.test(file.name) ||
      !['image/jpeg', ''].includes(file.type)
    ) {
      setError('Wybierz jeden plik JPEG (.jpg lub .jpeg).');
      return;
    }
    setUploading(true);
    setError('');
    try {
      const result = await client.uploadManualImageSelectionFile(
        runId,
        current.id,
        file.name,
        file,
      );
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się skopiować wybranego zdjęcia.',
          ),
        );
        return;
      }
      const previousUrl = drafts[current.id]?.previewUrl ?? '';
      if (previousUrl.startsWith('blob:')) {
        URL.revokeObjectURL(previousUrl);
        objectUrlsRef.current.delete(previousUrl);
      }
      const previewUrl = URL.createObjectURL(file);
      objectUrlsRef.current.add(previewUrl);
      updateDraft(current.id, {
        candidateId: result.data.candidate.id,
        fileName: result.data.candidate.displayName,
        idempotencyKey: null,
        previewUrl,
      });
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setUploading(false);
    }
  }

  async function approveCurrent() {
    if (
      current === undefined ||
      currentDraft === undefined ||
      approvalInFlightRef.current
    ) {
      return;
    }
    const rangeStart = parseOptionalSequence(currentDraft.rangeStart);
    const rangeEnd = parseOptionalSequence(currentDraft.rangeEnd);
    const hasCompleteRange = rangeStart !== null && rangeEnd !== null;
    const rangeInvalid =
      (rangeStart === null) !== (rangeEnd === null) ||
      (hasCompleteRange && rangeEnd < rangeStart);
    if (
      rangeInvalid ||
      (currentDraft.candidateId !== null && !hasCompleteRange)
    ) {
      setError(
        currentDraft.candidateId === null
          ? 'Podaj oba numery zakresu albo pozostaw oba pola puste.'
          : 'Aby zachować zdjęcie, podaj dodatni, rosnący zakres layoutów.',
      );
      return;
    }
    const idempotencyKey =
      currentDraft.idempotencyKey ?? window.crypto.randomUUID();
    updateDraft(current.id, { idempotencyKey });
    approvalInFlightRef.current = true;
    setApproving(true);
    setError('');
    try {
      const result =
        currentDraft.candidateId === null
          ? await client.continueImageSelectionWithoutImage(runId, current.id, {
              idempotencyKey,
              ...(rangeEnd === null ? {} : { rangeEnd }),
              ...(rangeStart === null ? {} : { rangeStart }),
            })
          : await client.approveManualImageSelection(runId, current.id, {
              candidateId: currentDraft.candidateId,
              idempotencyKey,
              rangeEnd,
              rangeStart,
            });
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się zapisać ręcznej decyzji.',
          ),
        );
        return;
      }
      handleApproval(result.data);
    } catch {
      setError(
        'Połączenie zostało przerwane. Ponowienie użyje tego samego klucza decyzji.',
      );
    } finally {
      approvalInFlightRef.current = false;
      setApproving(false);
    }
  }

  function handleApproval(result: ImageSelectionManualApprovalResponse) {
    updateDraft(result.group.id, {
      idempotencyKey: null,
      rangeEnd:
        result.group.rangeEnd === null ? '' : String(result.group.rangeEnd),
      rangeStart:
        result.group.rangeStart === null ? '' : String(result.group.rangeStart),
    });
    onGroupUpdated(result.group);
    if (groups.length > 1) setIndex((value) => (value + 1) % groups.length);
  }

  function handleDialogKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement;
    const editsText = ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName);
    if (event.key === 'ArrowLeft' && !editsText) {
      event.preventDefault();
      navigate(-1);
    } else if (event.key === 'ArrowRight' && !editsText) {
      event.preventDefault();
      navigate(1);
    } else if (event.key === 'Enter' && !event.repeat) {
      event.preventDefault();
      void approveCurrent();
    } else if (event.key === 'Escape') {
      event.preventDefault();
      onClose();
    }
  }

  if (current === undefined || currentDraft === undefined) return null;
  const displayedRangeStart = Number(currentDraft.rangeStart);
  const displayedRangeEnd = Number(currentDraft.rangeEnd);
  const hasDisplayedRange =
    Number.isInteger(displayedRangeStart) &&
    Number.isInteger(displayedRangeEnd) &&
    displayedRangeStart >= 1 &&
    displayedRangeEnd >= displayedRangeStart;
  const rangeLabel = !hasDisplayedRange
    ? 'Nierozpoznany zestaw zdjęć'
    : currentDraft.candidateId === null
      ? `Brak zdjęcia dla layoutów ${displayedRangeStart}–${displayedRangeEnd}`
      : `Layouty ${displayedRangeStart}–${displayedRangeEnd}`;

  return (
    <div className="manualSelectionOverlay">
      <div
        aria-labelledby="manual-selection-title"
        aria-modal="true"
        className="manualSelectionDialog"
        onKeyDown={handleDialogKeyDown}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="manualSelectionHeader">
          <div>
            <p className="eyebrow">
              {approvedCount} / {groups.length} zatwierdzonych
            </p>
            <h2 id="manual-selection-title">{rangeLabel}</h2>
          </div>
          <nav aria-label="Nawigacja między wyjątkami">
            <button
              aria-label="Poprzedni wyjątek"
              className="secondaryButton"
              disabled={groups.length < 2 || uploading || approving}
              onClick={() => navigate(-1)}
              type="button"
            >
              ←
            </button>
            <span>
              {index + 1} / {groups.length}
            </span>
            <button
              aria-label="Następny wyjątek"
              className="secondaryButton"
              disabled={groups.length < 2 || uploading || approving}
              onClick={() => navigate(1)}
              type="button"
            >
              →
            </button>
          </nav>
          <button
            className="primaryButton"
            disabled={approving || uploading}
            onClick={() => void approveCurrent()}
            type="button"
          >
            {approving
              ? 'Zapisywanie…'
              : currentDraft.candidateId === null
                ? 'Pomiń'
                : 'Zatwierdź'}
          </button>
          <button
            aria-label="Zamknij ręczną selekcję"
            className="secondaryButton"
            disabled={approving || uploading}
            onClick={onClose}
            type="button"
          >
            Zamknij
          </button>
        </header>

        {error ? (
          <p className="feedbackBanner feedbackBannerError" role="alert">
            {error}
          </p>
        ) : null}

        <div className="manualSelectionBody">
          <div className="manualSelectionPreview">
            {currentDraft.previewUrl ? (
              // The URL is either a local object URL or a scoped Admin API asset.
              // eslint-disable-next-line @next/next/no-img-element
              <img
                alt={`Wybrane zdjęcie: ${currentDraft.fileName}`}
                src={currentDraft.previewUrl}
              />
            ) : (
              <p>
                Możesz kontynuować bez zdjęcia albo opcjonalnie dodać jeden
                czytelny plik JPEG dla tego zestawu.
              </p>
            )}
          </div>
          <aside className="manualSelectionControls">
            <input
              accept=".jpg,.jpeg,image/jpeg"
              hidden
              onChange={(event) => void chooseFile(event)}
              ref={fileInputRef}
              type="file"
            />
            <button
              className="secondaryButton"
              disabled={uploading || approving}
              onClick={() => fileInputRef.current?.click()}
              type="button"
            >
              {uploading ? 'Kopiowanie…' : 'Dodaj opcjonalne zdjęcie'}
            </button>
            <span className="manualSelectionFileName">
              {currentDraft.fileName || 'Brak zdjęcia — możesz kontynuować'}
            </span>
            {currentDraft.candidateId !== null || hasDisplayedRange ? (
              <>
                <label>
                  Początek zakresu
                  <input
                    inputMode="numeric"
                    min={1}
                    onChange={(event) =>
                      updateDraft(current.id, {
                        rangeStart: event.target.value,
                      })
                    }
                    type="number"
                    value={currentDraft.rangeStart}
                  />
                </label>
                <label>
                  Koniec zakresu
                  <input
                    inputMode="numeric"
                    min={1}
                    onChange={(event) =>
                      updateDraft(current.id, { rangeEnd: event.target.value })
                    }
                    type="number"
                    value={currentDraft.rangeEnd}
                  />
                </label>
              </>
            ) : (
              <p>
                Nie musisz rozpoznawać numerów. Ten zestaw zostanie pominięty, a
                pewne zdjęcia przejdą dalej.
              </p>
            )}
            <p>
              ← / → nawigują · Enter zatwierdza · zapisany wybór możesz później
              poprawić
            </p>
          </aside>
        </div>
      </div>
    </div>
  );
}

function parseOptionalSequence(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : null;
}

function buildInitialDrafts(
  apiBaseUrl: string,
  runId: string,
  groups: readonly ImageSelectionGroupResponse[],
): Record<string, ManualDraft> {
  return Object.fromEntries(
    groups.map((group) => {
      const candidateId = group.selectedCandidateId;
      return [
        group.id,
        {
          candidateId,
          fileName: candidateId === null ? '' : 'Zapisane zdjęcie.jpg',
          idempotencyKey: null,
          previewUrl:
            candidateId === null
              ? ''
              : manualFileUrl(apiBaseUrl, runId, group.id, candidateId),
          rangeEnd: group.rangeEnd === null ? '' : String(group.rangeEnd),
          rangeStart: group.rangeStart === null ? '' : String(group.rangeStart),
        },
      ];
    }),
  );
}

function manualFileUrl(
  apiBaseUrl: string,
  runId: string,
  groupId: string,
  candidateId: string,
): string {
  return `${apiBaseUrl.replace(/\/$/, '')}/admin/image-selections/${encodeURIComponent(runId)}/groups/${encodeURIComponent(groupId)}/manual-files/${encodeURIComponent(candidateId)}`;
}

function firstPendingIndex(
  groups: readonly ImageSelectionGroupResponse[],
): number {
  const index = groups.findIndex((group) => group.status === 'manual_required');
  return index < 0 ? 0 : index;
}
