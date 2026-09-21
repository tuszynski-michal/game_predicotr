'use client';

import type { SemiAutomaticSelectionRunResponse } from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  ManualImageViewer,
  useManualImageViewer,
} from '@/features/manual-image-selection/manual-image-viewer';

import type { SemiAutomaticReviewSourceFile } from './semi-automatic-selection-actions.ts';
import type { SemiAutomaticSelectionLocalUiState } from './semi-automatic-selection-output-storage.ts';

interface V7SelectionReviewWorkspaceProps {
  readonly initialUi: SemiAutomaticSelectionLocalUiState | null;
  readonly onPersistUi: (
    ui: SemiAutomaticSelectionLocalUiState,
  ) => Promise<void>;
  readonly run: SemiAutomaticSelectionRunResponse;
  readonly sourceFiles: readonly SemiAutomaticReviewSourceFile[];
}

/**
 * Read-only source navigation for V7. It persists the exact neighbouring source
 * inspected by an operator, but cannot create or replace output files.
 */
export function V7SelectionReviewWorkspace({
  initialUi,
  onPersistUi,
  run,
  sourceFiles,
}: V7SelectionReviewWorkspaceProps) {
  const [sourceIndex, setSourceIndex] = useState(() =>
    clampSourceIndex(initialUi?.viewSourceIndex ?? 0, sourceFiles.length),
  );
  const restoredUiRef = useRef(initialUi);
  const restoredViewAppliedRef = useRef(initialUi !== null);
  const [error, setError] = useState('');
  const onViewerError = useCallback((message: string) => setError(message), []);
  const viewerFiles = useMemo(
    () =>
      sourceFiles.map((source) => ({
        handle: source.handle,
        relativePath: source.relativePath,
      })),
    [sourceFiles],
  );
  const persistView = useCallback(
    (view: {
      readonly scrollLeft: number;
      readonly scrollTop: number;
      readonly zoom: number;
    }) => {
      const restoredUi = restoredUiRef.current;
      const nextUi: SemiAutomaticSelectionLocalUiState = {
        activeExpectedIndex: restoredUi?.activeExpectedIndex ?? null,
        mode: 'review',
        scanSourceIndex: restoredUi?.scanSourceIndex ?? null,
        sequenceExpectedIndex: restoredUi?.sequenceExpectedIndex ?? null,
        scrollLeft: view.scrollLeft,
        scrollTop: view.scrollTop,
        viewSourceIndex: sourceIndex,
        zoomPercent: Math.round(view.zoom * 100),
      };
      restoredUiRef.current = nextUi;
      void onPersistUi(nextUi);
    },
    [onPersistUi, sourceIndex],
  );
  const viewer = useManualImageViewer(
    viewerFiles,
    sourceIndex,
    onViewerError,
    {
      scrollLeft: initialUi?.scrollLeft ?? 0,
      scrollTop: initialUi?.scrollTop ?? 0,
      zoom: (initialUi?.zoomPercent ?? 100) / 100,
    },
    persistView,
  );

  useEffect(() => {
    if (initialUi === null || restoredViewAppliedRef.current) return;
    restoredUiRef.current = initialUi;
    restoredViewAppliedRef.current = true;
    setSourceIndex(
      clampSourceIndex(initialUi.viewSourceIndex ?? 0, sourceFiles.length),
    );
  }, [initialUi, sourceFiles.length]);

  if (sourceFiles.length === 0) return null;
  return (
    <section className="semiAutomaticSelectionReview" aria-label="Podgląd V7">
      <div className="semiAutomaticSelectionReviewHeading">
        <div>
          <p className="eyebrow">PODGLĄD SĄSIADÓW V7</p>
          <h2>Zdjęcie źródłowe {sourceIndex + 1}</h2>
          <p>
            Run {run.id.slice(0, 8)} · podgląd nie zmienia reprezentanta ani
            kursora sekwencji.
          </p>
        </div>
        <span className="semiAutomaticSelectionCapability loading">
          Tylko podgląd
        </span>
      </div>
      {error !== '' ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      <ManualImageViewer
        busy={false}
        currentLabel="Podgląd sąsiedniego zdjęcia"
        currentPosition={sourceIndex + 1}
        currentRelativePath={sourceFiles[sourceIndex]?.relativePath ?? null}
        imageCount={sourceFiles.length}
        navigationStepLabel="←/→: sąsiednie zdjęcie · podgląd nie zatwierdza wyboru"
        nextDisabled={sourceIndex >= sourceFiles.length - 1}
        onNext={() =>
          setSourceIndex((current) =>
            Math.min(sourceFiles.length - 1, current + 1),
          )
        }
        onPrevious={() => setSourceIndex((current) => Math.max(0, current - 1))}
        previousDisabled={sourceIndex <= 0}
        state={viewer}
      />
    </section>
  );
}

function clampSourceIndex(sourceIndex: number, sourceCount: number): number {
  if (!Number.isSafeInteger(sourceIndex) || sourceIndex < 0) return 0;
  return Math.min(Math.max(0, sourceCount - 1), sourceIndex);
}
