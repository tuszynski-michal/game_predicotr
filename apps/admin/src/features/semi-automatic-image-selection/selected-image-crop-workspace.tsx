'use client';

import {
  createDefaultSelectedImageCropBand,
  validateSelectedImageCropBand,
  type SelectedImageCropBand,
} from '@game-predictor/manual-image-selection-core/crop';
import {
  SELECTED_IMAGE_AUTO_CROP_POLICY,
  type SelectedImageAutoCropProposal,
} from '@game-predictor/manual-image-selection-core/auto-crop';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  ManualImageViewer,
  useManualImageViewer,
  type ManualImageViewerInitialView,
} from '@/features/manual-image-selection/manual-image-viewer';

import {
  SelectedImageCropLocalStore,
  type SelectedImageCropLocalSession,
} from './selected-image-crop-local-store';
import {
  clearSelectedImageCropCorrections,
  completeSelectedImageCropCorrection,
  completeSelectedImageCropReview,
  listSelectedImageCropSourceDirectories,
  pickSelectedImageCropParentDirectory,
  prepareAllSelectedImageCrops,
  prepareSelectedImageCropDirectory,
  proposeSelectedImageCrop,
  recalculateUnreviewedSelectedImageCrops,
  saveSelectedImageCrop,
  setSelectedImageCropCorrection,
  type PreparedSelectedImageCropDirectory,
  type SelectedImageCropSourceSelection,
} from './selected-image-crop-storage';
import {
  loadSelectedImageCropAtlases,
  selectedImageCropAtlasPosition,
  SELECTED_IMAGE_CROP_THUMBNAIL_HEIGHT,
  SELECTED_IMAGE_CROP_THUMBNAIL_WIDTH,
  type SelectedImageCropAtlas,
} from './selected-image-crop-atlases';

const EMPTY_VIEW: ManualImageViewerInitialView = {
  scrollLeft: 0,
  scrollTop: 0,
  zoom: 1,
};

export function SelectedImageCropWorkspace() {
  const store = useMemo(() => new SelectedImageCropLocalStore(), []);
  const [parentDirectory, setParentDirectory] =
    useState<FileSystemDirectoryHandle | null>(null);
  const [directoryNames, setDirectoryNames] = useState<readonly string[]>([]);
  const [sourceDirectoryName, setSourceDirectoryName] = useState('');
  const [sourceSelection, setSourceSelection] =
    useState<SelectedImageCropSourceSelection>('all');
  const [prepared, setPrepared] =
    useState<PreparedSelectedImageCropDirectory | null>(null);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [crop, setCrop] = useState<SelectedImageCropBand | null>(null);
  const [proposal, setProposal] =
    useState<SelectedImageAutoCropProposal | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [preparationProgress, setPreparationProgress] = useState<{
    readonly completed: number;
    readonly total: number;
  } | null>(null);
  const [atlases, setAtlases] = useState<
    ReadonlyMap<number, SelectedImageCropAtlas>
  >(new Map());
  const [atlasesRequested, setAtlasesRequested] = useState(false);
  const [atlasesLoading, setAtlasesLoading] = useState(false);
  const [reviewFilter, setReviewFilter] = useState<
    'all' | 'uncertain' | 'correction' | 'failed'
  >('all');
  const [correctionMode, setCorrectionMode] = useState(false);
  const [initialView, setInitialView] = useState(EMPTY_VIEW);
  const viewRef = useRef<ManualImageViewerInitialView>(EMPTY_VIEW);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const restoredRef = useRef<SelectedImageCropLocalSession | null>(null);
  const proposalCacheRef = useRef(
    new Map<string, Promise<SelectedImageAutoCropProposal>>(),
  );
  const atlasAbortRef = useRef<AbortController | null>(null);
  const preparationAbortRef = useRef<AbortController | null>(null);
  const atlasesRequestedRef = useRef(false);

  const handleViewerError = useCallback(
    (message: string) => setError(message),
    [],
  );
  const handleViewChange = useCallback((view: ManualImageViewerInitialView) => {
    viewRef.current = view;
  }, []);
  const images = prepared?.sourceFiles ?? [];
  const viewerImages = correctionMode ? images : [];
  const viewer = useManualImageViewer(
    viewerImages,
    currentIndex,
    handleViewerError,
    initialView,
    handleViewChange,
  );
  const currentFile = images[currentIndex] ?? null;
  const manifest = prepared?.manifest ?? null;
  const currentEntry = manifest?.entries[currentIndex] ?? null;
  const preparedCount =
    manifest?.entries.filter((entry) => entry.result !== null).length ?? 0;
  const correctionFileNames = new Set(
    prepared?.snapshot.review.correctionFileNames ?? [],
  );
  const correctedFileNames = new Set(
    prepared?.snapshot.review.correctedFileNames ?? [],
  );
  const failures = prepared?.snapshot.session.failures ?? [];
  const done =
    prepared?.snapshot.review.completedAt !== null && prepared !== null;
  const policyRecalculationRequired =
    prepared !== null &&
    prepared.snapshot.session.preparationPolicyVersion !==
      SELECTED_IMAGE_AUTO_CROP_POLICY;
  const applyPrepared = useCallback(
    (result: PreparedSelectedImageCropDirectory, requestedIndex: number) => {
      const index = Math.min(
        Math.max(0, requestedIndex),
        result.sourceFiles.length - 1,
      );
      setPrepared(result);
      setCurrentIndex(index);
      setCrop(null);
      setProposal(null);
    },
    [],
  );

  const rebuildAtlases = useCallback(
    async (result: PreparedSelectedImageCropDirectory) => {
      atlasAbortRef.current?.abort();
      const controller = new AbortController();
      atlasAbortRef.current = controller;
      setAtlases((current) => {
        for (const atlas of current.values())
          URL.revokeObjectURL(atlas.imageUrl);
        return new Map();
      });
      setAtlasesLoading(true);
      try {
        await loadSelectedImageCropAtlases(
          result,
          (atlas) =>
            setAtlases((current) => {
              const next = new Map(current);
              const previous = next.get(atlas.batchIndex);
              if (previous !== undefined)
                URL.revokeObjectURL(previous.imageUrl);
              next.set(atlas.batchIndex, atlas);
              return next;
            }),
          controller.signal,
        );
      } catch (cause) {
        if (!controller.signal.aborted) setError(errorMessage(cause));
      } finally {
        if (!controller.signal.aborted) setAtlasesLoading(false);
      }
    },
    [],
  );

  useEffect(
    () => () => {
      atlasAbortRef.current?.abort();
      preparationAbortRef.current?.abort();
    },
    [],
  );

  const prepareForReview = useCallback(
    (result: PreparedSelectedImageCropDirectory, requestedIndex: number) => {
      preparationAbortRef.current?.abort();
      const preparationController = new AbortController();
      preparationAbortRef.current = preparationController;
      atlasAbortRef.current?.abort();
      atlasesRequestedRef.current = false;
      setAtlasesRequested(false);
      setAtlasesLoading(false);
      setAtlases((current) => {
        for (const atlas of current.values())
          URL.revokeObjectURL(atlas.imageUrl);
        return new Map();
      });
      applyPrepared(result, requestedIndex);
      const missing = result.manifest.entries.filter(
        (entry) => entry.result === null,
      ).length;
      if (missing === 0) {
        preparationAbortRef.current = null;
        setPreparationProgress(null);
        setNotice(
          result.snapshot.review.completedAt === null
            ? 'Wszystkie cropy są przygotowane. Miniaturki wczytasz na żądanie.'
            : 'Przegląd jest zakończony. Możesz wybrać inny katalog.',
        );
        return;
      }
      if (
        result.snapshot.session.preparationPolicyVersion !==
        SELECTED_IMAGE_AUTO_CROP_POLICY
      ) {
        preparationAbortRef.current = null;
        setPreparationProgress(null);
        setNotice(
          'To sesja przypięta do starszej polityki. Użyj „Przelicz nieprzejrzane nowym detektorem”, aby jawnie przejść na v5 i przygotować brakujące pliki.',
        );
        return;
      }
      setPreparationProgress({
        completed: result.manifest.entries.length - missing,
        total: result.manifest.entries.length,
      });
      setNotice('Automat wykrywa plansze i przygotowuje katalog cut…');
      void prepareAllSelectedImageCrops(
        result,
        (progress) => {
          if (preparationController.signal.aborted) return;
          setPrepared(progress.prepared);
          setPreparationProgress({
            completed: progress.completed,
            total: progress.total,
          });
        },
        undefined,
        preparationController.signal,
      )
        .then((completed) => {
          if (preparationController.signal.aborted) return;
          applyPrepared(completed.prepared, requestedIndex);
          setPreparationProgress(null);
          if (atlasesRequestedRef.current)
            void rebuildAtlases(completed.prepared);
          setNotice(
            completed.failures.length > 0
              ? `Przygotowano dostępne cropy. Błędy: ${completed.failures.length}.`
              : 'Wszystkie cropy są przygotowane. Wybierz miniaturki do poprawy.',
          );
        })
        .catch((cause: unknown) => {
          if (preparationController.signal.aborted) return;
          setPreparationProgress(null);
          setError(errorMessage(cause));
        });
    },
    [applyPrepared, rebuildAtlases],
  );

  useEffect(() => {
    let cancelled = false;
    void store.load().then((saved) => {
      if (cancelled || saved === null) return;
      restoredRef.current = saved;
      setParentDirectory(saved.parentDirectory);
      setSourceDirectoryName(saved.sourceDirectoryName);
      setSourceSelection(saved.sourceSelection ?? 'all');
      const view = {
        scrollLeft: saved.scrollLeft,
        scrollTop: saved.scrollTop,
        zoom: saved.zoom,
      };
      viewRef.current = view;
      setInitialView(view);
      setNotice(
        'Znaleziono zapisaną sesję. Kliknij „Wznów zapisany katalog”, aby nadać dostęp.',
      );
    });
    return () => {
      cancelled = true;
    };
  }, [store]);

  useEffect(() => {
    if (
      prepared === null ||
      viewer.sourceImageSize === null ||
      currentFile === null
    )
      return;
    const sourceSize = viewer.sourceImageSize;
    const persisted = manifest?.entries[currentIndex]?.result?.crop;
    if (persisted !== undefined) {
      if (
        persisted.width !== sourceSize.width ||
        persisted.height !== sourceSize.height
      )
        return;
      let cancelled = false;
      queueMicrotask(() => {
        if (cancelled) return;
        setCrop(persisted);
        setProposal(null);
        setDetecting(false);
      });
      return () => {
        cancelled = true;
      };
    }

    let cancelled = false;
    const key = `${currentFile.relativePath}:${currentFile.sizeBytes}:${currentFile.lastModifiedMs}`;
    let pending = proposalCacheRef.current.get(key);
    if (pending === undefined) {
      pending = currentFile.handle
        .getFile()
        .then((file) => proposeSelectedImageCrop(file));
      proposalCacheRef.current.set(key, pending);
    }
    queueMicrotask(() => {
      if (cancelled) return;
      setCrop(null);
      setProposal(null);
      setDetecting(true);
    });
    void pending
      .then((nextProposal) => {
        if (cancelled) return;
        setProposal(nextProposal);
        setCrop(nextProposal.crop);
        setDetecting(false);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const fallback = createDefaultSelectedImageCropBand(sourceSize);
        setCrop(fallback);
        setProposal(null);
        setDetecting(false);
        setNotice(
          `Automat nie wyznaczył granic. Sprawdź ręcznie propozycję (${errorMessage(cause)}).`,
        );
      });
    return () => {
      cancelled = true;
    };
  }, [currentFile, currentIndex, manifest, prepared, viewer.sourceImageSize]);

  useEffect(() => {
    if (
      parentDirectory === null ||
      sourceDirectoryName === '' ||
      prepared === null
    )
      return;
    const timeout = window.setTimeout(() => {
      void store.save({
        parentDirectory,
        sourceDirectoryName,
        sourceSelection,
        currentIndex,
        ...viewRef.current,
        updatedAt: new Date().toISOString(),
      });
    }, 150);
    return () => window.clearTimeout(timeout);
  }, [
    currentIndex,
    parentDirectory,
    prepared,
    sourceDirectoryName,
    sourceSelection,
    store,
    viewer.zoom,
  ]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        prepared === null ||
        !correctionMode ||
        busy ||
        detecting ||
        isEditableTarget(event.target)
      )
        return;
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        goPrevious();
      } else if (
        event.key.toLocaleLowerCase('pl-PL') === 'f' ||
        event.key === 'ArrowRight'
      ) {
        event.preventDefault();
        void saveCurrentCorrection();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  async function chooseParent() {
    leavePreparedWorkspace(false);
    setError('');
    setNotice('');
    try {
      const parent = await pickSelectedImageCropParentDirectory();
      setBusy(true);
      const names = await listSelectedImageCropSourceDirectories(parent);
      setParentDirectory(parent);
      restoredRef.current = null;
      setDirectoryNames(names);
      setSourceDirectoryName(names[0] ?? '');
      setSourceSelection('all');
      setPrepared(null);
      setAtlases(new Map());
      if (names.length === 0)
        setNotice('Katalog nadrzędny nie zawiera katalogów źródłowych.');
    } catch (cause) {
      if (!(cause instanceof DOMException && cause.name === 'AbortError'))
        setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function startOrResume() {
    if (parentDirectory === null || sourceDirectoryName === '') return;
    setBusy(true);
    setError('');
    setNotice('Sprawdzam źródła i manifest…');
    try {
      const result = await prepareSelectedImageCropDirectory(
        parentDirectory,
        sourceDirectoryName,
        sourceSelection,
      );
      prepareForReview(
        result,
        restoredRef.current?.currentIndex ?? result.manifest.currentIndex,
      );
    } catch (cause) {
      setError(errorMessage(cause));
      setNotice('');
    } finally {
      setBusy(false);
    }
  }

  function leavePreparedWorkspace(clearDirectory = true) {
    preparationAbortRef.current?.abort();
    preparationAbortRef.current = null;
    atlasAbortRef.current?.abort();
    atlasAbortRef.current = null;
    for (const atlas of atlases.values()) URL.revokeObjectURL(atlas.imageUrl);
    atlasesRequestedRef.current = false;
    setAtlasesRequested(false);
    setAtlasesLoading(false);
    setAtlases(new Map());
    setPrepared(null);
    setPreparationProgress(null);
    setCorrectionMode(false);
    setCrop(null);
    setProposal(null);
    setDetecting(false);
    setBusy(false);
    if (clearDirectory) {
      restoredRef.current = null;
      setParentDirectory(null);
      setDirectoryNames([]);
      setSourceDirectoryName('');
      setSourceSelection('all');
      setNotice('Sesja została zachowana. Możesz wybrać inny katalog.');
    }
  }

  function requestAtlases() {
    if (prepared === null || atlasesLoading) return;
    atlasesRequestedRef.current = true;
    setAtlasesRequested(true);
    void rebuildAtlases(prepared);
  }

  async function saveCurrentCorrection() {
    if (
      prepared === null ||
      manifest === null ||
      currentFile === null ||
      crop === null
    )
      return;
    setBusy(true);
    setError('');
    setNotice('Zapisuję crop i weryfikuję checksumę…');
    try {
      const updated = await saveSelectedImageCrop({
        prepared,
        sourceFile: currentFile,
        crop: validateSelectedImageCropBand(crop),
      });
      let final = updated;
      if (correctionMode) {
        final = await completeSelectedImageCropCorrection({
          prepared: updated,
          fileName: currentFile.fileName,
        });
      }
      setPrepared(final);
      if (correctionMode) {
        const remaining = final.snapshot.review.correctionFileNames;
        if (remaining.length === 0) {
          setCorrectionMode(false);
          if (atlasesRequestedRef.current) void rebuildAtlases(final);
        } else {
          const nextName = remaining[0]!;
          setCurrentIndex(
            final.sourceFiles.findIndex((item) => item.fileName === nextName),
          );
        }
      } else {
        setCurrentIndex(final.manifest.currentIndex);
      }
      setNotice(
        final.manifest.entries.every((entry) => entry.result !== null)
          ? `Crop poprawiony. Katalog „${final.manifest.outputDirectoryName}” jest kompletny.`
          : 'Crop zapisany i zweryfikowany.',
      );
    } catch (cause) {
      setError(errorMessage(cause));
      setNotice('');
    } finally {
      setBusy(false);
    }
  }

  function goPrevious() {
    if (prepared === null) return;
    const queue = prepared.snapshot.review.correctionFileNames;
    const position = queue.indexOf(currentFile?.fileName ?? '');
    if (position <= 0) return;
    const previousName = queue[position - 1]!;
    setCurrentIndex(
      prepared.sourceFiles.findIndex((item) => item.fileName === previousName),
    );
  }
  function resetCrop() {
    if (viewer.sourceImageSize === null) return;
    const persisted = currentEntry?.result?.crop;
    setCrop(
      persisted ??
        proposal?.crop ??
        createDefaultSelectedImageCropBand(viewer.sourceImageSize),
    );
  }

  const failureNames = new Set(failures.map((failure) => failure.fileName));
  const visibleEntries = (manifest?.entries ?? [])
    .map((entry, index) => ({ entry, index }))
    .filter(({ entry }) => {
      if (reviewFilter === 'correction')
        return correctionFileNames.has(entry.fileName);
      if (reviewFilter === 'failed') return failureNames.has(entry.fileName);
      if (reviewFilter === 'uncertain')
        return (
          entry.result?.autoCropProposal?.classification === 'conservative' ||
          entry.result?.autoCropProposal?.classification === 'safe_wide'
        );
      return true;
    });

  async function recalculateUnreviewed() {
    if (prepared === null || preparationProgress !== null || busy) return;
    preparationAbortRef.current?.abort();
    const controller = new AbortController();
    preparationAbortRef.current = controller;
    setPreparationProgress({ completed: 0, total: images.length });
    setError('');
    setNotice(
      'Przeliczam wyłącznie nieprzejrzane i niepoprawiane ręcznie cropy…',
    );
    try {
      const result = await recalculateUnreviewedSelectedImageCrops(
        prepared,
        (progress) => {
          if (controller.signal.aborted) return;
          setPrepared(progress.prepared);
          setPreparationProgress({
            completed: progress.completed,
            total: progress.total,
          });
        },
        controller.signal,
      );
      if (controller.signal.aborted) return;
      setPrepared(result.prepared);
      setPreparationProgress(null);
      if (atlasesRequestedRef.current) void rebuildAtlases(result.prepared);
      setNotice(
        result.failures.length === 0
          ? 'Nieprzejrzane cropy przeliczono detektorem v5.'
          : `Przeliczanie zakończone. Błędy: ${result.failures.length}.`,
      );
    } catch (cause) {
      if (!controller.signal.aborted) {
        setPreparationProgress(null);
        setError(errorMessage(cause));
      }
    }
  }

  async function toggleCorrection(fileName: string) {
    if (prepared === null || busy) return;
    setBusy(true);
    setError('');
    try {
      const updated = await setSelectedImageCropCorrection({
        prepared,
        fileName,
        selected: !correctionFileNames.has(fileName),
      });
      setPrepared(updated);
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  function beginCorrections() {
    if (
      prepared === null ||
      prepared.snapshot.review.correctionFileNames.length === 0
    )
      return;
    const firstName = prepared.snapshot.review.correctionFileNames[0]!;
    const index = prepared.sourceFiles.findIndex(
      (item) => item.fileName === firstName,
    );
    if (index < 0) return;
    setCurrentIndex(index);
    setCorrectionMode(true);
  }

  async function retryFailures() {
    if (
      prepared === null ||
      failures.length === 0 ||
      preparationProgress !== null
    )
      return;
    preparationAbortRef.current?.abort();
    const preparationController = new AbortController();
    preparationAbortRef.current = preparationController;
    setPreparationProgress({ completed: preparedCount, total: images.length });
    setError('');
    const retryNames = new Set(failures.map((failure) => failure.fileName));
    const result = await prepareAllSelectedImageCrops(
      prepared,
      (progress) => {
        setPrepared(progress.prepared);
        setPreparationProgress({
          completed: progress.completed,
          total: progress.total,
        });
      },
      retryNames,
      preparationController.signal,
    );
    if (preparationController.signal.aborted) return;
    setPrepared(result.prepared);
    setPreparationProgress(null);
    if (atlasesRequestedRef.current) void rebuildAtlases(result.prepared);
    setNotice(
      result.failures.length === 0
        ? 'Błędne pliki zostały przygotowane.'
        : `Nadal nie udało się przygotować ${result.failures.length} plików.`,
    );
  }

  async function clearCorrections() {
    if (prepared === null || busy) return;
    setBusy(true);
    try {
      setPrepared(await clearSelectedImageCropCorrections(prepared));
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function finishReview() {
    if (prepared === null) return;
    setBusy(true);
    setError('');
    try {
      const updated = await completeSelectedImageCropReview(prepared);
      setPrepared(updated);
      setNotice(
        `Gotowe. Do importu wybierz katalog „${updated.manifest.outputDirectoryName}”.`,
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="semiAutomaticSelectionSetup selectedImageCropWorkspace">
      <div className="semiAutomaticSelectionSetupHeader">
        <div>
          <span className="eyebrow">Niezależnie od gry · lokalnie</span>
          <h2>Przytnij wybrane zdjęcia</h2>
          <p>
            Usuń tło nad i pod planszami. Źródła pozostaną bez zmian, a JPEG-i
            trafią do sąsiedniego katalogu z końcówką „cut”.
          </p>
        </div>
      </div>

      {prepared === null ? (
        <div className="selectedImageCropSetup">
          <button
            className="secondaryButton"
            disabled={busy}
            onClick={() => void chooseParent()}
            type="button"
          >
            Wybierz katalog nadrzędny
          </button>
          {parentDirectory !== null ? (
            <span>{parentDirectory.name}</span>
          ) : null}
          {directoryNames.length > 0 ? (
            <label>
              Katalog z plikami seq_*
              <select
                disabled={busy}
                onChange={(event) => setSourceDirectoryName(event.target.value)}
                value={sourceDirectoryName}
              >
                {directoryNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {parentDirectory !== null && sourceDirectoryName !== '' ? (
            <label>
              Zakres do przycięcia
              <select
                disabled={busy}
                onChange={(event) =>
                  setSourceSelection(
                    event.target.value as SelectedImageCropSourceSelection,
                  )
                }
                value={sourceSelection}
              >
                <option value="all">Wszystkie pliki seq_*</option>
                <option value="filled_gaps">
                  Tylko uzupełnione luki z manifestu
                </option>
              </select>
            </label>
          ) : null}
          {parentDirectory !== null && sourceDirectoryName !== '' ? (
            <button
              className="primaryButton"
              disabled={busy}
              onClick={() => void startOrResume()}
              type="button"
            >
              {restoredRef.current === null
                ? 'Rozpocznij lub wznów'
                : 'Wznów zapisany katalog'}
            </button>
          ) : null}
        </div>
      ) : (
        <div className="selectedImageCropReview">
          <div className="selectedImageCropProgress">
            <strong>
              {preparationProgress !== null
                ? `Przygotowywanie ${preparationProgress.completed} / ${preparationProgress.total}`
                : done
                  ? 'Gotowe'
                  : `Przygotowano ${preparedCount} / ${images.length}`}
            </strong>
            <progress
              max={images.length}
              value={preparationProgress?.completed ?? preparedCount}
            />
            <span>{manifest?.outputDirectoryName}</span>
            <span>{proposalLabel(proposal, detecting)}</span>
            <button
              className="secondaryButton"
              disabled={busy}
              onClick={() => leavePreparedWorkspace()}
              type="button"
            >
              Wyjdź i wybierz inny katalog
            </button>
          </div>
          {correctionMode ? (
            <>
              <ManualImageViewer
                busy={busy || detecting}
                currentLabel={currentFile?.fileName ?? 'Brak zdjęcia'}
                currentPosition={
                  correctionFileNames.has(currentFile?.fileName ?? '')
                    ? prepared.snapshot.review.correctionFileNames.indexOf(
                        currentFile?.fileName ?? '',
                      ) + 1
                    : 1
                }
                currentRelativePath={currentFile?.relativePath ?? null}
                imageCount={correctionFileNames.size}
                imageOverlay={
                  crop === null ? null : (
                    <CropBandOverlay
                      crop={crop}
                      disabled={busy || detecting}
                      onChange={setCrop}
                    />
                  )
                }
                navigationStepLabel={`do poprawy: ${correctionFileNames.size}`}
                nextDisabled={false}
                onNext={() => void saveCurrentCorrection()}
                onPrevious={goPrevious}
                previousDisabled={
                  prepared.snapshot.review.correctionFileNames.indexOf(
                    currentFile?.fileName ?? '',
                  ) <= 0
                }
                state={viewer}
                toolbarStart={
                  <>
                    <button
                      className="secondaryButton"
                      disabled={busy}
                      onClick={() => setCorrectionMode(false)}
                      type="button"
                    >
                      Wróć do miniaturek
                    </button>
                    <button
                      className="secondaryButton"
                      disabled={busy || detecting || crop === null}
                      onClick={resetCrop}
                      type="button"
                    >
                      Resetuj cięcie
                    </button>
                  </>
                }
              />
              <div className="manualImageSelectionActions selectedImageCropActions">
                <button
                  className="primaryButton"
                  disabled={busy || detecting || crop === null}
                  onClick={() => void saveCurrentCorrection()}
                  type="button"
                >
                  Zapisz poprawkę
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="selectedImageCropGridToolbar">
                <div
                  className="selectedImageCropFilters"
                  role="group"
                  aria-label="Filtr miniaturek"
                >
                  <button
                    className={
                      reviewFilter === 'all'
                        ? 'primaryButton'
                        : 'secondaryButton'
                    }
                    onClick={() => setReviewFilter('all')}
                    type="button"
                  >
                    Wszystkie
                  </button>
                  <button
                    className={
                      reviewFilter === 'uncertain'
                        ? 'primaryButton'
                        : 'secondaryButton'
                    }
                    onClick={() => setReviewFilter('uncertain')}
                    type="button"
                  >
                    Niepewne
                  </button>
                  <button
                    className={
                      reviewFilter === 'correction'
                        ? 'primaryButton'
                        : 'secondaryButton'
                    }
                    onClick={() => setReviewFilter('correction')}
                    type="button"
                  >
                    Do poprawy ({correctionFileNames.size})
                  </button>
                  <button
                    className={
                      reviewFilter === 'failed'
                        ? 'primaryButton'
                        : 'secondaryButton'
                    }
                    onClick={() => setReviewFilter('failed')}
                    type="button"
                  >
                    Błędy ({failures.length})
                  </button>
                </div>
                <strong>Zaznaczone: {correctionFileNames.size}</strong>
                <button
                  className="secondaryButton"
                  disabled={busy || preparationProgress !== null || done}
                  onClick={() => void recalculateUnreviewed()}
                  type="button"
                >
                  {policyRecalculationRequired
                    ? 'Przejdź na v5 i przelicz nieprzejrzane'
                    : 'Przelicz nieprzejrzane nowym detektorem'}
                </button>
                <button
                  className="secondaryButton"
                  disabled={atlasesLoading || preparedCount === 0}
                  onClick={requestAtlases}
                  type="button"
                >
                  {atlasesLoading
                    ? 'Wczytywanie miniaturek…'
                    : atlasesRequested
                      ? `Odśwież miniaturki (${atlases.size})`
                      : 'Wczytaj miniaturki'}
                </button>
                <button
                  className="secondaryButton"
                  disabled={busy || correctionFileNames.size === 0}
                  onClick={() => void clearCorrections()}
                  type="button"
                >
                  Wyczyść zaznaczenie
                </button>
                <button
                  className="primaryButton"
                  disabled={busy || correctionFileNames.size === 0}
                  onClick={beginCorrections}
                  type="button"
                >
                  Popraw zaznaczone ({correctionFileNames.size})
                </button>
                <button
                  className="secondaryButton"
                  disabled={
                    busy ||
                    failures.length === 0 ||
                    preparationProgress !== null
                  }
                  onClick={() => void retryFailures()}
                  type="button"
                >
                  Ponów błędne
                </button>
                <button
                  className="primaryButton"
                  disabled={
                    busy ||
                    preparationProgress !== null ||
                    failures.length > 0 ||
                    correctionFileNames.size > 0 ||
                    preparedCount !== images.length ||
                    done
                  }
                  onClick={() => void finishReview()}
                  type="button"
                >
                  Zatwierdź i zakończ przegląd
                </button>
              </div>
              <div
                className="selectedImageCropGrid"
                aria-label="Miniaturki przyciętych zdjęć"
              >
                {visibleEntries.map(({ entry, index }) => {
                  const position = selectedImageCropAtlasPosition(index);
                  const atlas = atlases.get(position.batchIndex);
                  const selected = correctionFileNames.has(entry.fileName);
                  const failure = failures.find(
                    (item) => item.fileName === entry.fileName,
                  );
                  return (
                    <button
                      aria-pressed={selected}
                      className={`selectedImageCropTile${selected ? ' isSelected' : ''}${failure !== undefined ? ' hasError' : ''}`}
                      disabled={busy || entry.result === null}
                      key={entry.fileName}
                      onClick={() => void toggleCorrection(entry.fileName)}
                      title={
                        failure === undefined
                          ? entry.fileName
                          : `${entry.fileName}: ${failure.stage} — ${failure.code}`
                      }
                      type="button"
                    >
                      {atlas === undefined ||
                      !atlas.fileNames.includes(entry.fileName) ? (
                        <span className="selectedImageCropTilePlaceholder">
                          {failure === undefined
                            ? atlasesRequested
                              ? 'Przygotowywanie…'
                              : 'Miniaturka niewczytana'
                            : 'Błąd przygotowania'}
                        </span>
                      ) : (
                        <span
                          className="selectedImageCropTileImage"
                          style={{
                            backgroundImage: `url(${atlas.imageUrl})`,
                            backgroundPosition: `-${position.x}px -${position.y}px`,
                            width: SELECTED_IMAGE_CROP_THUMBNAIL_WIDTH,
                            height: SELECTED_IMAGE_CROP_THUMBNAIL_HEIGHT,
                          }}
                        />
                      )}
                      <span className="selectedImageCropTileLabel">
                        {entry.fileName}
                      </span>
                      {selected ? (
                        <span className="selectedImageCropTileBadge">
                          Do poprawy
                        </span>
                      ) : correctedFileNames.has(entry.fileName) ? (
                        <span className="selectedImageCropTileBadge isCorrected">
                          Poprawiony
                        </span>
                      ) : (
                        <ProposalBadge
                          proposal={entry.result?.autoCropProposal ?? null}
                        />
                      )}
                    </button>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}
      {notice !== '' ? <p className="noticeMessage">{notice}</p> : null}
      {error !== '' ? <p className="errorMessage">{error}</p> : null}
    </section>
  );
}

function ProposalBadge({
  proposal,
}: {
  readonly proposal: SelectedImageAutoCropProposal | null;
}) {
  if (proposal === null) return null;
  if (proposal.classification === 'high_confidence')
    return <span className="selectedImageCropTileBadge isCertain">Pewne</span>;
  if (proposal.classification === 'conservative')
    return (
      <span className="selectedImageCropTileBadge isConservative">
        Zachowawcze
      </span>
    );
  return (
    <span className="selectedImageCropTileBadge isWide">
      Szerokie — sprawdź
    </span>
  );
}

function CropBandOverlay({
  crop,
  disabled,
  onChange,
}: {
  readonly crop: SelectedImageCropBand;
  readonly disabled: boolean;
  readonly onChange: (crop: SelectedImageCropBand) => void;
}) {
  const overlayRef = useRef<HTMLDivElement | null>(null);
  function startDrag(edge: 'top' | 'bottom', event: React.PointerEvent) {
    if (disabled) return;
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    const move = (moveEvent: PointerEvent) => {
      const bounds = overlayRef.current?.getBoundingClientRect();
      if (bounds === undefined) return;
      const y = Math.round(
        Math.min(
          1,
          Math.max(0, (moveEvent.clientY - bounds.top) / bounds.height),
        ) * crop.height,
      );
      try {
        onChange(
          validateSelectedImageCropBand({
            ...crop,
            topY: edge === 'top' ? y : crop.topY,
            bottomY: edge === 'bottom' ? y : crop.bottomY,
          }),
        );
      } catch {
        // Keep the last valid band while the pointer crosses a protected bound.
      }
    };
    const stop = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', stop);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', stop, { once: true });
  }
  const top = (crop.topY / crop.height) * 100;
  const bottom = (crop.bottomY / crop.height) * 100;
  return (
    <div className="selectedImageCropOverlay" ref={overlayRef}>
      <div
        className="selectedImageCropShade"
        style={{ height: `${top}%`, top: 0 }}
      />
      <div
        className="selectedImageCropShade"
        style={{ bottom: 0, height: `${100 - bottom}%` }}
      />
      <div
        aria-label="Górna linia cięcia"
        aria-valuemax={crop.bottomY}
        aria-valuemin={0}
        aria-valuenow={crop.topY}
        className="selectedImageCropLine"
        onPointerDown={(event) => startDrag('top', event)}
        role="slider"
        style={{ top: `${top}%` }}
        tabIndex={0}
      />
      <div
        aria-label="Dolna linia cięcia"
        aria-valuemax={crop.height}
        aria-valuemin={crop.topY}
        aria-valuenow={crop.bottomY}
        className="selectedImageCropLine"
        onPointerDown={(event) => startDrag('bottom', event)}
        role="slider"
        style={{ top: `${bottom}%` }}
        tabIndex={0}
      />
    </div>
  );
}

function proposalLabel(
  proposal: SelectedImageAutoCropProposal | null,
  detecting: boolean,
): string {
  if (detecting) return 'Automat wykrywa obszar plansz…';
  if (proposal === null) return 'Zapisane cięcie';
  if (proposal.classification === 'safe_wide')
    return 'Brak pewnej granicy — sprawdź i przesuń linie';
  const quality =
    proposal.classification === 'high_confidence' ? 'pewna' : 'zachowawcza';
  return `Automatyczna propozycja wielokolumnowa · ${quality} · ${Math.round(proposal.confidence * 100)}%`;
}

function isEditableTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName))
  );
}

function errorMessage(cause: unknown): string {
  if (!(cause instanceof Error))
    return 'Nie udało się przygotować przyciętych zdjęć.';
  if (cause.message === 'SELECTED_IMAGE_CROP_FILLED_GAPS_MANIFEST_MISSING')
    return 'Ten katalog nie ma manifestu korekty z uzupełnionymi lukami.';
  if (cause.message === 'SELECTED_IMAGE_CROP_FILLED_GAPS_EMPTY')
    return 'Manifest nie zawiera aktywnych uzupełnień do przycięcia.';
  if (cause.message.startsWith('SELECTED_IMAGE_CROP_FILLED_GAP_MISSING:'))
    return `Brakuje pliku zapisanego w manifeście: ${cause.message.split(':')[1]}.`;
  if (cause.message.startsWith('SELECTED_IMAGE_CROP_FILLED_GAP_CHANGED:'))
    return `Plik uzupełnienia zmienił się od zapisu manifestu: ${cause.message.split(':')[1]}.`;
  return cause.message;
}
