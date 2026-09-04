'use client';

import {
  createDefaultSelectedImageCropBand,
  validateSelectedImageCropBand,
  type SelectedImageCropBand,
  type SelectedImageCropManifestV1,
} from '@game-predictor/manual-image-selection-core/crop';
import type { SelectedImageAutoCropProposal } from '@game-predictor/manual-image-selection-core/auto-crop';
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
  listSelectedImageCropSourceDirectories,
  pickSelectedImageCropParentDirectory,
  prepareSelectedImageCropDirectory,
  proposeSelectedImageCrop,
  saveSelectedImageCrop,
  type PreparedSelectedImageCropDirectory,
} from './selected-image-crop-storage';

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
  const [prepared, setPrepared] =
    useState<PreparedSelectedImageCropDirectory | null>(null);
  const [manifest, setManifest] = useState<SelectedImageCropManifestV1 | null>(
    null,
  );
  const [currentIndex, setCurrentIndex] = useState(0);
  const [crop, setCrop] = useState<SelectedImageCropBand | null>(null);
  const [proposal, setProposal] =
    useState<SelectedImageAutoCropProposal | null>(null);
  const [detecting, setDetecting] = useState(false);
  const [initialView, setInitialView] = useState(EMPTY_VIEW);
  const viewRef = useRef<ManualImageViewerInitialView>(EMPTY_VIEW);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const restoredRef = useRef<SelectedImageCropLocalSession | null>(null);
  const proposalCacheRef = useRef(
    new Map<string, Promise<SelectedImageAutoCropProposal>>(),
  );

  const handleViewerError = useCallback(
    (message: string) => setError(message),
    [],
  );
  const handleViewChange = useCallback((view: ManualImageViewerInitialView) => {
    viewRef.current = view;
  }, []);
  const images = prepared?.sourceFiles ?? [];
  const viewer = useManualImageViewer(
    images,
    currentIndex,
    handleViewerError,
    initialView,
    handleViewChange,
  );
  const currentFile = images[currentIndex] ?? null;
  const currentEntry = manifest?.entries[currentIndex] ?? null;
  const acceptedCount =
    manifest?.entries.filter((entry) => entry.result !== null).length ?? 0;
  const done = manifest !== null && acceptedCount === manifest.entries.length;
  const dirtyAccepted =
    currentEntry !== null &&
    currentEntry.result !== null &&
    crop !== null &&
    !sameCrop(currentEntry.result.crop, crop);

  useEffect(() => {
    let cancelled = false;
    void store.load().then((saved) => {
      if (cancelled || saved === null) return;
      restoredRef.current = saved;
      setParentDirectory(saved.parentDirectory);
      setSourceDirectoryName(saved.sourceDirectoryName);
      const view = {
        scrollLeft: saved.scrollLeft,
        scrollTop: saved.scrollTop,
        zoom: saved.zoom,
      };
      viewRef.current = view;
      setInitialView(view);
      void restorePrepared(saved).catch(() => {
        setNotice(
          'Zapisana sesja wymaga ponownego nadania dostępu do katalogu.',
        );
      });
    });
    return () => {
      cancelled = true;
    };
    async function restorePrepared(saved: SelectedImageCropLocalSession) {
      const result = await prepareSelectedImageCropDirectory(
        saved.parentDirectory,
        saved.sourceDirectoryName,
      );
      if (cancelled) return;
      applyPrepared(result, saved.currentIndex);
    }
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
    if (
      persisted !== undefined &&
      persisted.width === sourceSize.width &&
      persisted.height === sourceSize.height
    ) {
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
    store,
    viewer.zoom,
  ]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        prepared === null ||
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
        void saveOrAdvance(false);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  async function chooseParent() {
    setError('');
    setNotice('');
    try {
      const parent = await pickSelectedImageCropParentDirectory();
      setBusy(true);
      const names = await listSelectedImageCropSourceDirectories(parent);
      setParentDirectory(parent);
      setDirectoryNames(names);
      setSourceDirectoryName(names[0] ?? '');
      setPrepared(null);
      setManifest(null);
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
      );
      applyPrepared(
        result,
        restoredRef.current?.currentIndex ?? result.manifest.currentIndex,
      );
      setNotice(
        result.manifest.revision > 0
          ? 'Wznowiono trwałą sesję przycinania.'
          : 'Utworzono bezpieczny katalog wynikowy.',
      );
    } catch (cause) {
      setError(errorMessage(cause));
      setNotice('');
    } finally {
      setBusy(false);
    }
  }

  function applyPrepared(
    result: PreparedSelectedImageCropDirectory,
    requestedIndex: number,
  ) {
    const index = Math.min(
      Math.max(0, requestedIndex),
      result.sourceFiles.length - 1,
    );
    setPrepared(result);
    setManifest(result.manifest);
    setCurrentIndex(index);
    setCrop(null);
    setProposal(null);
  }

  async function saveOrAdvance(forceOverwrite: boolean) {
    if (
      prepared === null ||
      manifest === null ||
      currentFile === null ||
      crop === null
    )
      return;
    if (dirtyAccepted && !forceOverwrite) {
      setNotice(
        'Zmieniono zatwierdzone cięcie. Użyj przycisku „Zapisz ponownie”.',
      );
      return;
    }
    if (
      currentEntry !== null &&
      currentEntry.result !== null &&
      !dirtyAccepted &&
      !forceOverwrite
    ) {
      goNext();
      return;
    }
    setBusy(true);
    setError('');
    setNotice('Zapisuję crop i weryfikuję checksumę…');
    try {
      const updated = await saveSelectedImageCrop({
        outputDirectory: prepared.outputDirectory,
        sourceFile: currentFile,
        crop: validateSelectedImageCropBand(crop),
        manifest,
      });
      setManifest(updated);
      setCurrentIndex(updated.currentIndex);
      setNotice(
        updated.entries.every((entry) => entry.result !== null)
          ? `Gotowe. Do importu wybierz katalog „${updated.outputDirectoryName}”.`
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
    setCurrentIndex((value) => Math.max(0, value - 1));
  }
  function goNext() {
    setCurrentIndex((value) => Math.min(images.length - 1, value + 1));
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
            <button
              className="primaryButton"
              disabled={busy}
              onClick={() => void startOrResume()}
              type="button"
            >
              Rozpocznij lub wznów
            </button>
          ) : null}
        </div>
      ) : (
        <div className="selectedImageCropReview">
          <div className="selectedImageCropProgress">
            <strong>
              {done ? 'Gotowe' : `${acceptedCount} / ${images.length}`}
            </strong>
            <progress max={images.length} value={acceptedCount} />
            <span>{manifest?.outputDirectoryName}</span>
            <span>{proposalLabel(proposal, detecting)}</span>
          </div>
          <ManualImageViewer
            busy={busy || detecting}
            currentLabel={currentFile?.fileName ?? 'Brak zdjęcia'}
            currentPosition={currentIndex + 1}
            currentRelativePath={currentFile?.relativePath ?? null}
            imageCount={images.length}
            imageOverlay={
              crop === null ? null : (
                <CropBandOverlay
                  crop={crop}
                  disabled={busy || detecting}
                  onChange={setCrop}
                />
              )
            }
            navigationStepLabel="skok: 1"
            nextDisabled={false}
            onNext={() => void saveOrAdvance(false)}
            onPrevious={goPrevious}
            previousDisabled={currentIndex === 0}
            state={viewer}
            toolbarStart={
              <button
                className="secondaryButton"
                disabled={busy || detecting || crop === null}
                onClick={resetCrop}
                type="button"
              >
                Resetuj cięcie
              </button>
            }
          />
          <div className="manualImageSelectionActions selectedImageCropActions">
            <button
              className="primaryButton"
              disabled={
                busy || detecting || crop === null || (done && !dirtyAccepted)
              }
              onClick={() => void saveOrAdvance(dirtyAccepted)}
              type="button"
            >
              {dirtyAccepted ? 'Zapisz ponownie' : 'Zapisz i przejdź dalej'}
            </button>
          </div>
        </div>
      )}
      {notice !== '' ? <p className="noticeMessage">{notice}</p> : null}
      {error !== '' ? <p className="errorMessage">{error}</p> : null}
    </section>
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

function sameCrop(
  left: SelectedImageCropBand,
  right: SelectedImageCropBand,
): boolean {
  return (
    left.width === right.width &&
    left.height === right.height &&
    left.topY === right.topY &&
    left.bottomY === right.bottomY
  );
}

function proposalLabel(
  proposal: SelectedImageAutoCropProposal | null,
  detecting: boolean,
): string {
  if (detecting) return 'Automat wykrywa obszar plansz…';
  if (proposal === null) return 'Zapisane cięcie';
  if (proposal.strategy === 'safe_default')
    return 'Brak pewnej granicy — sprawdź i przesuń linie';
  const strategy =
    proposal.strategy === 'chromatic_panel'
      ? 'wykryty panel plansz'
      : 'wykryty obszar szczegółów';
  return `Automatyczna propozycja · ${strategy} · ${Math.round(proposal.confidence * 100)}%`;
}

function isEditableTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName))
  );
}

function errorMessage(cause: unknown): string {
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się przygotować przyciętych zdjęć.';
}
