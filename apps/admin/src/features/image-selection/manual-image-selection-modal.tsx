'use client';

import type {
  ImageSelectionGroupCandidatesResponse,
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
import {
  defaultManualCandidateIndex,
  nextUnresolvedManualIndex,
} from './manual-image-selection-policy';

interface ManualImageSelectionModalProps {
  readonly apiBaseUrl: string;
  readonly client: ImageSelectionClient;
  readonly groups: readonly ImageSelectionGroupResponse[];
  readonly mode?: 'manual' | 'range' | 'rejected' | 'automatic-verification';
  readonly onClose: () => void;
  readonly onGroupUpdated: (
    group: ImageSelectionGroupResponse,
  ) => Promise<string | null>;
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

interface GroupSourceSummary {
  readonly data: ImageSelectionGroupCandidatesResponse | null;
  readonly error: boolean;
  readonly loading: boolean;
}

interface DuplicateRangeConflict {
  readonly groupId: string;
  readonly idempotencyKey: string;
  readonly rangeEnd: number;
  readonly rangeStart: number;
}

export function ManualImageSelectionModal({
  apiBaseUrl,
  client,
  groups,
  mode = 'manual',
  onClose,
  onGroupUpdated,
  runId,
}: ManualImageSelectionModalProps) {
  const verificationMode = mode === 'automatic-verification';
  const rangeMode = mode === 'range';
  const rejectedMode = mode === 'rejected';
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const approvalInFlightRef = useRef(false);
  const objectUrlsRef = useRef(new Set<string>());
  const sourceRequestsRef = useRef(new Set<string>());
  const [index, setIndex] = useState(() => firstPendingIndex(groups, mode));
  const [drafts, setDrafts] = useState<Record<string, ManualDraft>>(() =>
    buildInitialDrafts(apiBaseUrl, runId, groups),
  );
  const [uploading, setUploading] = useState(false);
  const [approving, setApproving] = useState(false);
  const [error, setError] = useState('');
  const [duplicateRangeConflict, setDuplicateRangeConflict] =
    useState<DuplicateRangeConflict | null>(null);
  const [fullScreenPreviewOpen, setFullScreenPreviewOpen] = useState(false);
  const [previewZoomed, setPreviewZoomed] = useState(false);
  const [sourceSummaries, setSourceSummaries] = useState<
    Record<string, GroupSourceSummary>
  >({});
  const current = groups[index];
  const currentDraft = current === undefined ? undefined : drafts[current.id];
  const currentSourceSummary =
    current === undefined ? undefined : sourceSummaries[current.id];
  const decisionCounts = useMemo(() => {
    const selected = groups.filter(
      (group) => !isPendingGroup(group, mode),
    ).length;
    const skipped = groups.filter(
      (group) => group.status === 'missing_image',
    ).length;
    return {
      remaining: groups.filter((group) => isPendingGroup(group, mode)).length,
      selected,
      skipped,
    };
  }, [groups, mode]);

  useEffect(() => {
    const objectUrls = objectUrlsRef.current;
    dialogRef.current?.focus();
    return () => {
      for (const url of objectUrls) URL.revokeObjectURL(url);
      objectUrls.clear();
    };
  }, []);

  useEffect(() => {
    if (current === undefined || sourceRequestsRef.current.has(current.id)) {
      return;
    }
    const groupId = current.id;
    sourceRequestsRef.current.add(groupId);
    setSourceSummaries((value) => ({
      ...value,
      [groupId]: { data: null, error: false, loading: true },
    }));
    void client
      .listImageSelectionGroupCandidates(runId, groupId, { limit: 500 })
      .then((result) => {
        const candidates = result.data?.items;
        setSourceSummaries((value) => ({
          ...value,
          [groupId]: {
            data: result.data ?? null,
            error: result.error !== undefined || result.data === undefined,
            loading: false,
          },
        }));
        if (candidates === undefined || candidates.length === 0) return;
        setDrafts((value) => {
          const existing = value[groupId];
          if (existing === undefined) return value;
          const candidate =
            (existing.candidateId === null
              ? candidates[defaultManualCandidateIndex(candidates.length) ?? -1]
              : candidates.find((item) => item.id === existing.candidateId)) ??
            null;
          if (candidate === null) return value;
          const previewUrl = candidateFileUrl(
            apiBaseUrl,
            runId,
            groupId,
            candidate.id,
          );
          if (
            existing.candidateId === candidate.id &&
            existing.fileName === candidate.displayName &&
            existing.previewUrl === previewUrl
          ) {
            return value;
          }
          return {
            ...value,
            [groupId]: {
              ...existing,
              candidateId: candidate.id,
              fileName: candidate.displayName,
              idempotencyKey: null,
              previewUrl,
            },
          };
        });
      })
      .catch(() => {
        setSourceSummaries((value) => ({
          ...value,
          [groupId]: { data: null, error: true, loading: false },
        }));
      });
  }, [apiBaseUrl, client, current, runId]);

  function navigate(offset: number) {
    if (groups.length < 2 || uploading || approving) return;
    closeFullScreenPreview();
    setError('');
    setDuplicateRangeConflict(null);
    setIndex((value) => (value + offset + groups.length) % groups.length);
  }

  function closeFullScreenPreview() {
    setFullScreenPreviewOpen(false);
    setPreviewZoomed(false);
  }

  function updateDraft(groupId: string, patch: Partial<ManualDraft>) {
    setDrafts((value) => {
      const existing = value[groupId];
      if (existing === undefined) return value;
      return { ...value, [groupId]: { ...existing, ...patch } };
    });
  }

  function updateRangeDraft(
    groupId: string,
    field: 'rangeEnd' | 'rangeStart',
    value: string,
  ) {
    setDuplicateRangeConflict(null);
    setError('');
    updateDraft(groupId, { [field]: value });
  }

  function chooseCandidate(candidateId: string, fileName: string) {
    if (current === undefined || uploading || approving || rejectedMode) return;
    const previousUrl = drafts[current.id]?.previewUrl ?? '';
    if (previousUrl.startsWith('blob:')) {
      URL.revokeObjectURL(previousUrl);
      objectUrlsRef.current.delete(previousUrl);
    }
    updateDraft(current.id, {
      candidateId,
      fileName,
      idempotencyKey: null,
      previewUrl: candidateFileUrl(apiBaseUrl, runId, current.id, candidateId),
    });
  }

  async function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    input.value = '';
    if (
      verificationMode ||
      rangeMode ||
      rejectedMode ||
      current === undefined ||
      file === undefined
    )
      return;
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

  async function approveCurrent(candidateOverride?: {
    readonly candidateId: string;
    readonly fileName: string;
  }) {
    if (
      verificationMode ||
      current === undefined ||
      currentDraft === undefined ||
      approvalInFlightRef.current
    ) {
      return;
    }
    if (rejectedMode) {
      await restoreCurrent();
      return;
    }
    const defaultCandidate =
      currentSourceSummary?.data?.items[
        defaultManualCandidateIndex(currentSourceSummary.data.items.length) ??
          -1
      ];
    const draftForApproval =
      candidateOverride !== undefined
        ? {
            ...currentDraft,
            candidateId: candidateOverride.candidateId,
            fileName: candidateOverride.fileName,
            previewUrl: candidateFileUrl(
              apiBaseUrl,
              runId,
              current.id,
              candidateOverride.candidateId,
            ),
          }
        : currentDraft.candidateId === null && defaultCandidate !== undefined
          ? {
              ...currentDraft,
              candidateId: defaultCandidate.id,
              fileName: defaultCandidate.displayName,
              previewUrl: candidateFileUrl(
                apiBaseUrl,
                runId,
                current.id,
                defaultCandidate.id,
              ),
            }
          : currentDraft;
    if (
      current.status === 'manual_required' &&
      draftForApproval.candidateId === null &&
      (currentSourceSummary === undefined || currentSourceSummary.loading)
    ) {
      setError('Poczekaj, aż galeria wybierze domyślne zdjęcie.');
      return;
    }
    const rangeStart = parseOptionalSequence(draftForApproval.rangeStart);
    const enteredRangeEnd = parseOptionalSequence(draftForApproval.rangeEnd);
    const rangeEnd =
      rangeMode && rangeStart !== null && enteredRangeEnd === null
        ? rangeStart + 8
        : enteredRangeEnd;
    const hasCompleteRange = rangeStart !== null && rangeEnd !== null;
    const rangeInvalid =
      (rangeStart === null) !== (rangeEnd === null) ||
      (hasCompleteRange &&
        (rangeEnd < rangeStart ||
          (rangeMode && rangeEnd - rangeStart + 1 > 9)));
    if (
      rangeInvalid ||
      (draftForApproval.candidateId !== null && !hasCompleteRange) ||
      (rangeMode && draftForApproval.candidateId === null)
    ) {
      setError(
        draftForApproval.candidateId === null
          ? 'Podaj oba numery zakresu albo pozostaw oba pola puste.'
          : 'Aby zachować zdjęcie, podaj dodatni, rosnący zakres layoutów.',
      );
      return;
    }
    if (
      duplicateRangeConflict?.groupId === current.id &&
      duplicateRangeConflict.rangeStart === rangeStart &&
      duplicateRangeConflict.rangeEnd === rangeEnd
    ) {
      await discardDuplicateCurrent();
      return;
    }
    const idempotencyKey =
      draftForApproval.idempotencyKey ?? window.crypto.randomUUID();
    updateDraft(current.id, { ...draftForApproval, idempotencyKey });
    approvalInFlightRef.current = true;
    setApproving(true);
    setError('');
    try {
      const result = rangeMode
        ? await client.confirmImageSelectionGroupRange(runId, current.id, {
            candidateId: draftForApproval.candidateId as string,
            idempotencyKey,
            ...(enteredRangeEnd === null ? {} : { rangeEnd: enteredRangeEnd }),
            rangeStart: rangeStart as number,
          })
        : draftForApproval.candidateId === null
          ? await client.continueImageSelectionWithoutImage(runId, current.id, {
              idempotencyKey,
              ...(rangeEnd === null ? {} : { rangeEnd }),
              ...(rangeStart === null ? {} : { rangeStart }),
            })
          : await client.approveManualImageSelection(runId, current.id, {
              candidateId: draftForApproval.candidateId,
              idempotencyKey,
              rangeEnd,
              rangeStart,
            });
      if (result.error !== undefined || result.data === undefined) {
        if (
          apiErrorCode(result.error) === 'IMAGE_SELECTION_RANGE_CONFLICT' &&
          rangeStart !== null &&
          rangeEnd !== null
        ) {
          setDuplicateRangeConflict({
            groupId: current.id,
            idempotencyKey: window.crypto.randomUUID(),
            rangeEnd,
            rangeStart,
          });
          setError(
            `Zakres ${rangeStart}–${rangeEnd} jest już używany przez inną wybraną grupę. Popraw zakres albo odrzuć tę grupę jako duplikat i przejdź dalej.`,
          );
          return;
        }
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się zapisać ręcznej decyzji.',
          ),
        );
        return;
      }
      await handleApproval(result.data);
    } catch {
      setError(
        'Połączenie zostało przerwane. Ponowienie użyje tego samego klucza decyzji.',
      );
    } finally {
      approvalInFlightRef.current = false;
      setApproving(false);
    }
  }

  async function discardDuplicateCurrent() {
    if (
      verificationMode ||
      current === undefined ||
      currentDraft === undefined ||
      approvalInFlightRef.current
    ) {
      return;
    }
    const rangeStart = parseOptionalSequence(currentDraft.rangeStart);
    const enteredRangeEnd = parseOptionalSequence(currentDraft.rangeEnd);
    const rangeEnd =
      rangeMode && rangeStart !== null && enteredRangeEnd === null
        ? rangeStart + 8
        : enteredRangeEnd;
    if (rangeStart === null || rangeEnd === null || rangeEnd < rangeStart) {
      setError('Podaj dodatni, rosnący zakres przed odrzuceniem duplikatu.');
      return;
    }
    const idempotencyKey =
      duplicateRangeConflict?.groupId === current.id &&
      duplicateRangeConflict.rangeStart === rangeStart &&
      duplicateRangeConflict.rangeEnd === rangeEnd
        ? duplicateRangeConflict.idempotencyKey
        : window.crypto.randomUUID();
    approvalInFlightRef.current = true;
    setApproving(true);
    setError('');
    try {
      const result = await client.discardDuplicateImageSelectionGroup(
        runId,
        current.id,
        { idempotencyKey, rangeEnd, rangeStart },
      );
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się odrzucić grupy jako duplikatu.',
          ),
        );
        return;
      }
      await handleApproval(result.data);
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      approvalInFlightRef.current = false;
      setApproving(false);
    }
  }

  async function rejectCurrent() {
    if (
      verificationMode ||
      rejectedMode ||
      current === undefined ||
      !isPendingGroup(current, mode) ||
      approvalInFlightRef.current
    )
      return;
    approvalInFlightRef.current = true;
    setApproving(true);
    setError('');
    try {
      const result = await client.rejectImageSelectionReviewGroup(
        runId,
        current.id,
        { idempotencyKey: window.crypto.randomUUID() },
      );
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Nie udało się odrzucić tej grupy.'),
        );
        return;
      }
      await handleApproval(result.data);
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      approvalInFlightRef.current = false;
      setApproving(false);
    }
  }

  async function restoreCurrent() {
    if (!rejectedMode || current === undefined || approvalInFlightRef.current)
      return;
    approvalInFlightRef.current = true;
    setApproving(true);
    setError('');
    try {
      const result = await client.restoreRejectedImageSelectionGroup(
        runId,
        current.id,
        { idempotencyKey: window.crypto.randomUUID() },
      );
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Nie udało się przywrócić tej grupy.'),
        );
        return;
      }
      await handleApproval(result.data);
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      approvalInFlightRef.current = false;
      setApproving(false);
    }
  }

  async function handleApproval(
    result: ImageSelectionManualApprovalResponse,
  ): Promise<void> {
    const outputError = await onGroupUpdated(result.group);
    if (outputError !== null) {
      setError(
        `Decyzja została zapisana w bazie, ale plik nie trafił do folderu: ${outputError} Użyj ponownie „Zatwierdź”, aby ponowić zapis.`,
      );
      return;
    }
    setDuplicateRangeConflict(null);
    setError('');
    updateDraft(result.group.id, {
      idempotencyKey: null,
      rangeEnd:
        result.group.rangeEnd === null ? '' : String(result.group.rangeEnd),
      rangeStart:
        result.group.rangeStart === null ? '' : String(result.group.rangeStart),
    });
    const removedFromQueue =
      result.group.status === 'skipped_existing_range' ||
      result.group.status === 'rejected_by_user' ||
      rejectedMode;
    const remainingGroups = removedFromQueue
      ? groups.filter((group) => group.id !== result.group.id)
      : groups;
    if (remainingGroups.length === 0) {
      onClose();
      return;
    }
    if (removedFromQueue) {
      const nextPendingId = findNextPendingGroupId(
        groups,
        result.group.id,
        mode,
      );
      const nextIndex = remainingGroups.findIndex(
        (group) => group.id === nextPendingId,
      );
      setIndex(nextIndex < 0 ? 0 : nextIndex);
      return;
    }
    if (groups.length > 1) {
      setIndex((value) =>
        nextUnresolvedManualIndex(
          groups.map(
            (group) =>
              group.id !== result.group.id && isPendingGroup(group, mode),
          ),
          value,
        ),
      );
    }
  }

  function handleDialogKeyDown(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (fullScreenPreviewOpen) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeFullScreenPreview();
      }
      return;
    }
    const target = event.target as HTMLElement;
    const editsText = ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName);
    const activatesButton = target.closest('button') !== null;
    if (event.key === 'ArrowLeft' && !editsText) {
      event.preventDefault();
      navigate(-1);
    } else if (event.key === 'ArrowRight' && !editsText) {
      event.preventDefault();
      if (verificationMode) navigate(1);
      else void approveCurrent();
    } else if (event.key === 'Enter' && !event.repeat && !activatesButton) {
      event.preventDefault();
      if (verificationMode) navigate(1);
      else void approveCurrent();
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
    ? 'Zakres layoutów nierozpoznany'
    : currentDraft.candidateId === null
      ? `Brak zdjęcia dla layoutów ${displayedRangeStart}–${displayedRangeEnd}`
      : `Layouty ${displayedRangeStart}–${displayedRangeEnd}`;
  const sourceIdentity = groupSourceIdentity(
    current.groupOrder,
    currentSourceSummary,
  );
  const waitingForDefaultCandidate =
    current.status === 'manual_required' &&
    currentDraft.candidateId === null &&
    (currentSourceSummary === undefined || currentSourceSummary.loading);
  const algorithmCandidate = currentSourceSummary?.data?.items.find(
    (candidate) => candidate.id === current.selectedCandidateId,
  );

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
              {verificationMode ? (
                <>
                  Kontrola wyborów algorytmu · {index + 1} / {groups.length}
                </>
              ) : rangeMode ? (
                <>Ustalanie grupy · pozostało: {decisionCounts.remaining}</>
              ) : rejectedMode ? (
                <>
                  Odrzucone grupy · {index + 1} / {groups.length}
                </>
              ) : (
                <>
                  Wybrane: {decisionCounts.selected} · pominięte:{' '}
                  {decisionCounts.skipped} · pozostało:{' '}
                  {decisionCounts.remaining}
                </>
              )}
            </p>
            <h2 id="manual-selection-title">{rangeLabel}</h2>
            <p className="manualSelectionSourceIdentity">{sourceIdentity}</p>
          </div>
          <nav
            aria-label={
              verificationMode
                ? 'Nawigacja między automatycznymi wyborami'
                : rangeMode
                  ? 'Nawigacja między grupami bez rozpoznanego zakresu'
                  : rejectedMode
                    ? 'Nawigacja między odrzuconymi grupami'
                    : 'Nawigacja między wyjątkami'
            }
          >
            <button
              aria-label={
                verificationMode
                  ? 'Poprzedni wybór algorytmu'
                  : 'Poprzedni wyjątek'
              }
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
              aria-label={
                verificationMode
                  ? 'Następny wybór algorytmu'
                  : 'Zatwierdź i przejdź do następnego wyjątku'
              }
              className="secondaryButton"
              disabled={
                groups.length < 2 ||
                uploading ||
                approving ||
                waitingForDefaultCandidate
              }
              onClick={() =>
                verificationMode ? navigate(1) : void approveCurrent()
              }
              type="button"
            >
              →
            </button>
          </nav>
          <button
            className="primaryButton"
            disabled={
              approving ||
              uploading ||
              waitingForDefaultCandidate ||
              (verificationMode && groups.length < 2)
            }
            onClick={() =>
              verificationMode ? navigate(1) : void approveCurrent()
            }
            onKeyDown={(event) => event.stopPropagation()}
            type="button"
          >
            {verificationMode
              ? 'Następna grupa'
              : rejectedMode
                ? approving
                  ? 'Przywracanie…'
                  : 'Przywróć do kolejki'
                : rangeMode
                  ? approving
                    ? 'Zapisywanie…'
                    : 'Zatwierdź zakres'
                  : approving
                    ? 'Zapisywanie…'
                    : duplicateRangeConflict?.groupId === current.id
                      ? 'Odrzuć duplikat i dalej'
                      : currentDraft.candidateId === null
                        ? 'Pomiń'
                        : 'Zatwierdź'}
          </button>
          <button
            aria-label={
              verificationMode
                ? 'Zamknij kontrolę wyborów algorytmu'
                : rangeMode
                  ? 'Zamknij ustalanie grup'
                  : rejectedMode
                    ? 'Zamknij listę odrzuconych grup'
                    : 'Zamknij ręczną selekcję'
            }
            className="secondaryButton"
            disabled={approving || uploading}
            onClick={onClose}
            type="button"
          >
            Zamknij
          </button>
        </header>

        <div className="manualSelectionFeedbackSlot">
          {error ? (
            duplicateRangeConflict?.groupId === current.id ? (
              <div className="feedbackBanner feedbackBannerError" role="alert">
                <p>{error}</p>
                <button
                  className="primaryButton"
                  disabled={approving || uploading}
                  onClick={() => void discardDuplicateCurrent()}
                  onKeyDown={(event) => event.stopPropagation()}
                  type="button"
                >
                  {approving ? 'Zapisywanie…' : 'Odrzuć duplikat i dalej'}
                </button>
              </div>
            ) : (
              <p className="feedbackBanner feedbackBannerError" role="alert">
                {error}
              </p>
            )
          ) : null}
        </div>

        <div className="manualSelectionBody">
          <div className="manualSelectionPreview">
            {currentDraft.previewUrl ? (
              <button
                aria-label={`Otwórz pełny podgląd zdjęcia ${currentDraft.fileName}`}
                className="manualSelectionPreviewButton"
                onClick={() => setFullScreenPreviewOpen(true)}
                onKeyDown={(event) => event.stopPropagation()}
                type="button"
              >
                {/* The URL is either a local object URL or a scoped Admin API asset. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  alt={`Wybrane zdjęcie: ${currentDraft.fileName}`}
                  src={currentDraft.previewUrl}
                />
                <span className="manualSelectionPreviewAction">
                  <span aria-hidden="true">🔍</span> Pełny ekran
                </span>
              </button>
            ) : (
              <p>
                Możesz kontynuować bez zdjęcia albo opcjonalnie dodać jeden
                czytelny plik JPEG dla tego zestawu.
              </p>
            )}
          </div>
          <div
            aria-label="Zdjęcia należące do bieżącej grupy"
            className="manualSelectionCandidateGallery"
            role="region"
            tabIndex={0}
          >
            {currentSourceSummary?.loading ? (
              <p>Ładowanie miniaturek…</p>
            ) : null}
            {currentSourceSummary?.error ? (
              <p>Nie udało się pobrać zdjęć tej grupy.</p>
            ) : null}
            {currentSourceSummary?.data ? (
              <p className="manualSelectionCandidateGallerySummary">
                Zdjęcia: {currentSourceSummary.data.items.length} /{' '}
                {currentSourceSummary.data.sourceCount}
                {currentSourceSummary.data.items.length <
                currentSourceSummary.data.sourceCount
                  ? ' (starszy run zachował tylko shortlistę)'
                  : ''}
                {' · przewiń listę, aby zobaczyć wszystkie'}
              </p>
            ) : null}
            {currentSourceSummary?.data?.items.map((candidate) => {
              const selected = currentDraft.candidateId === candidate.id;
              const selectedByAlgorithm =
                current.selectedCandidateId === candidate.id;
              const previewUrl = candidateFileUrl(
                apiBaseUrl,
                runId,
                current.id,
                candidate.id,
              );
              return (
                <button
                  aria-pressed={selected}
                  className={[
                    'manualSelectionCandidate',
                    selected ? 'manualSelectionCandidateSelected' : '',
                    (verificationMode || rangeMode) && selectedByAlgorithm
                      ? 'manualSelectionCandidateAlgorithm'
                      : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  key={candidate.id}
                  disabled={rejectedMode}
                  onClick={() =>
                    chooseCandidate(candidate.id, candidate.displayName)
                  }
                  onKeyDown={(event) => {
                    if (event.key !== 'Enter' || event.repeat) return;
                    event.preventDefault();
                    event.stopPropagation();
                    chooseCandidate(candidate.id, candidate.displayName);
                    if (!verificationMode && !rangeMode && !rejectedMode) {
                      void approveCurrent({
                        candidateId: candidate.id,
                        fileName: candidate.displayName,
                      });
                    }
                  }}
                  type="button"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    alt={candidate.displayName}
                    loading="lazy"
                    src={previewUrl}
                  />
                  <span title={candidate.displayName}>
                    {candidate.displayName}
                  </span>
                  {(verificationMode || rangeMode) && selectedByAlgorithm ? (
                    <strong className="manualSelectionAlgorithmBadge">
                      Wybór algorytmu
                    </strong>
                  ) : null}
                </button>
              );
            })}
          </div>
          <aside className="manualSelectionControls">
            {verificationMode ? (
              <>
                <strong>Algorytm wybrał</strong>
                <span className="manualSelectionFileName">
                  {algorithmCandidate?.displayName ?? currentDraft.fileName}
                </span>
                <p>
                  Zdjęcie z oznaczeniem „Wybór algorytmu” jest zapisanym
                  reprezentantem. Klikaj pozostałe miniatury, aby porównać całą
                  grupę. Ten tryb niczego nie zmienia w jobie ani w katalogu.
                </p>
                <p>← wraca · → lub Enter przechodzi do następnej grupy</p>
              </>
            ) : rejectedMode ? (
              <>
                <strong>Grupa odrzucona przez użytkownika</strong>
                <p>
                  Przywrócenie przeniesie ją z powrotem dokładnie do kolejki
                  wyboru zdjęcia albo ustalania grupy.
                </p>
                <p>← wraca · → lub Enter przywraca grupę</p>
              </>
            ) : rangeMode ? (
              <>
                <strong>Wybierz najlepsze zdjęcie i podaj początek</strong>
                <span className="manualSelectionFileName">
                  {currentDraft.fileName || algorithmCandidate?.displayName}
                </span>
                <label>
                  Początek zakresu
                  <input
                    inputMode="numeric"
                    min={1}
                    onChange={(event) =>
                      updateRangeDraft(
                        current.id,
                        'rangeStart',
                        event.target.value,
                      )
                    }
                    type="number"
                    value={currentDraft.rangeStart}
                  />
                </label>
                <label>
                  Koniec zakresu (opcjonalnie)
                  <input
                    inputMode="numeric"
                    max={
                      parseOptionalSequence(currentDraft.rangeStart) === null
                        ? undefined
                        : (parseOptionalSequence(
                            currentDraft.rangeStart,
                          ) as number) + 8
                    }
                    min={1}
                    onChange={(event) =>
                      updateRangeDraft(
                        current.id,
                        'rangeEnd',
                        event.target.value,
                      )
                    }
                    type="number"
                    value={currentDraft.rangeEnd}
                  />
                </label>
                <p>
                  Puste pole końca oznacza dziewięć layoutów, czyli początek +
                  8. Wpisz koniec tylko dla krótszej grupy.
                </p>
                {current.status === 'range_required' ? (
                  <button
                    className="dangerButton"
                    disabled={uploading || approving}
                    onClick={() => void rejectCurrent()}
                    onKeyDown={(event) => event.stopPropagation()}
                    type="button"
                  >
                    Odrzuć grupę
                  </button>
                ) : null}
                <p>← wraca · → lub Enter zatwierdza zakres i idzie dalej</p>
              </>
            ) : (
              <>
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
                {current.status === 'manual_required' ? (
                  <button
                    className="dangerButton"
                    disabled={uploading || approving}
                    onClick={() => void rejectCurrent()}
                    onKeyDown={(event) => event.stopPropagation()}
                    type="button"
                  >
                    Odrzuć grupę
                  </button>
                ) : null}
                {current.status === 'manual_required' && hasDisplayedRange ? (
                  <button
                    className="secondaryButton"
                    disabled={uploading || approving}
                    onClick={() => void discardDuplicateCurrent()}
                    onKeyDown={(event) => event.stopPropagation()}
                    type="button"
                  >
                    Odrzuć jako duplikat
                  </button>
                ) : null}
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
                          updateRangeDraft(
                            current.id,
                            'rangeStart',
                            event.target.value,
                          )
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
                          updateRangeDraft(
                            current.id,
                            'rangeEnd',
                            event.target.value,
                          )
                        }
                        type="number"
                        value={currentDraft.rangeEnd}
                      />
                    </label>
                  </>
                ) : (
                  <p>
                    System nie potrafi wiarygodnie podać numerów layoutów dla
                    tego zestawu. Odszukaj go po nazwach plików pokazanych w
                    nagłówku albo pomiń — pewne zdjęcia nadal przejdą dalej.
                  </p>
                )}
                <p>
                  ← wraca · → lub Enter zatwierdza i przechodzi dalej · zapisany
                  wybór możesz później poprawić
                </p>
              </>
            )}
          </aside>
        </div>
        {fullScreenPreviewOpen && currentDraft.previewUrl ? (
          <div
            aria-label={`Pełny podgląd zdjęcia ${currentDraft.fileName}`}
            aria-modal="true"
            className="manualSelectionFullscreenOverlay"
            role="dialog"
          >
            <header className="manualSelectionFullscreenHeader">
              <strong>{currentDraft.fileName}</strong>
              <div>
                <button
                  aria-pressed={previewZoomed}
                  className="secondaryButton"
                  onClick={() => setPreviewZoomed((value) => !value)}
                  onKeyDown={(event) => event.stopPropagation()}
                  type="button"
                >
                  <span aria-hidden="true">🔍</span>{' '}
                  {previewZoomed ? 'Dopasuj' : 'Powiększ'}
                </button>
                <button
                  aria-label="Zamknij pełny podgląd"
                  className="secondaryButton"
                  onClick={closeFullScreenPreview}
                  onKeyDown={(event) => event.stopPropagation()}
                  type="button"
                >
                  Zamknij
                </button>
              </div>
            </header>
            <button
              aria-label={
                previewZoomed
                  ? 'Dopasuj zdjęcie do ekranu'
                  : 'Powiększ zdjęcie do rozmiaru oryginalnego'
              }
              className={
                previewZoomed
                  ? 'manualSelectionFullscreenPreview manualSelectionFullscreenPreviewZoomed'
                  : 'manualSelectionFullscreenPreview'
              }
              onClick={() => setPreviewZoomed((value) => !value)}
              onKeyDown={(event) => event.stopPropagation()}
              type="button"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                alt={`Pełny podgląd: ${currentDraft.fileName}`}
                src={currentDraft.previewUrl}
              />
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function groupSourceIdentity(
  groupOrder: number,
  summary: GroupSourceSummary | undefined,
): string {
  const prefix = `Zestaw #${groupOrder + 1}`;
  if (summary === undefined || summary.loading) {
    return `${prefix} · odczytywanie plików źródłowych…`;
  }
  if (summary.error || summary.data === null) {
    return `${prefix} · nie udało się odczytać nazw plików źródłowych`;
  }
  const names = summary.data.items.map((candidate) => candidate.displayName);
  const files =
    names.length === 0
      ? 'brak zapisanych kandydatów'
      : `pliki kandydatów: ${names.join(', ')}`;
  return `${prefix} · ${summary.data.sourceCount} zdjęć w zestawie · ${files}`;
}

function parseOptionalSequence(value: string): number | null {
  if (value.trim() === '') return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : null;
}

function apiErrorCode(error: unknown): string | null {
  if (
    typeof error !== 'object' ||
    error === null ||
    !('code' in error) ||
    typeof error.code !== 'string'
  ) {
    return null;
  }
  return error.code;
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
              : candidateFileUrl(apiBaseUrl, runId, group.id, candidateId),
          rangeEnd: group.rangeEnd === null ? '' : String(group.rangeEnd),
          rangeStart: group.rangeStart === null ? '' : String(group.rangeStart),
        },
      ];
    }),
  );
}

function candidateFileUrl(
  apiBaseUrl: string,
  runId: string,
  groupId: string,
  candidateId: string,
): string {
  return `${apiBaseUrl.replace(/\/$/, '')}/api/v1/admin/image-selections/${encodeURIComponent(runId)}/groups/${encodeURIComponent(groupId)}/candidates/${encodeURIComponent(candidateId)}/file`;
}

function firstPendingIndex(
  groups: readonly ImageSelectionGroupResponse[],
  mode: NonNullable<ManualImageSelectionModalProps['mode']>,
): number {
  const index = groups.findIndex((group) => isPendingGroup(group, mode));
  return index < 0 ? 0 : index;
}

function findNextPendingGroupId(
  groups: readonly ImageSelectionGroupResponse[],
  currentGroupId: string,
  mode: NonNullable<ManualImageSelectionModalProps['mode']>,
): string | null {
  const currentIndex = groups.findIndex((group) => group.id === currentGroupId);
  for (let offset = 1; offset < groups.length; offset += 1) {
    const candidate = groups[(currentIndex + offset) % groups.length];
    if (candidate !== undefined && isPendingGroup(candidate, mode)) {
      return candidate.id;
    }
  }
  return null;
}

function isPendingGroup(
  group: ImageSelectionGroupResponse,
  mode: NonNullable<ManualImageSelectionModalProps['mode']>,
): boolean {
  if (mode === 'range') return group.status === 'range_required';
  if (mode === 'rejected') return group.status === 'rejected_by_user';
  if (mode === 'automatic-verification') return true;
  return group.status === 'manual_required';
}
