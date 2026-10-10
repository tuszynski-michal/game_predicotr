'use client';

import type {
  OperationalImageReviewGeometryResponse,
  OperationalImageReviewItemResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { operationalBoardGeometryTarget } from './board-geometry-correction-target';
import { BoardGeometryCorrectionEditor } from './deferred-board-cell-geometry-editor';
import type { OperationalReviewsClient } from './operational-review-actions';

interface OperationalReviewGeometryEditorProps {
  readonly api: OperationalReviewsClient;
  readonly apiBaseUrl: string;
  readonly importJobId: string;
  readonly item: OperationalImageReviewItemResponse;
  readonly onSaved: (geometry: OperationalImageReviewGeometryResponse) => void;
}

/**
 * Grid correction of the board open in the operational review (TASK-0798).
 *
 * The dialog hosts the shared single-board editor of the correction queue:
 * the same corners, "Niepełna plansza" flags, qualification and validation,
 * sent through the operational routes of this item.
 */
export function OperationalReviewGeometryEditor({
  api,
  apiBaseUrl,
  importJobId,
  item,
  onSaved,
}: OperationalReviewGeometryEditorProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const [conflict, setConflict] = useState('');
  const target = useMemo(
    () =>
      operationalBoardGeometryTarget({ api, apiBaseUrl, importJobId, item }),
    [api, apiBaseUrl, importJobId, item],
  );

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const handleConflict = useCallback(async (message: string) => {
    setConflict(`${message} Zamknij edytor i przeładuj planszę.`);
  }, []);

  const handleSaved = useCallback(async () => {
    const geometry = target.takeSavedGeometry();
    setOpen(false);
    if (geometry !== null) onSaved(geometry);
  }, [onSaved, target]);

  function closeEditor() {
    setOpen(false);
    setConflict('');
  }

  return (
    <>
      <button
        className="textButton operationalReviewGeometryOpen"
        onClick={() => {
          setConflict('');
          setOpen(true);
        }}
        type="button"
      >
        Edytuj siatkę
      </button>
      <dialog
        aria-labelledby="operational-review-geometry-title"
        className="operationalReviewGeometryDialog"
        onCancel={(event) => {
          event.preventDefault();
          closeEditor();
        }}
        ref={dialogRef}
      >
        <header>
          <div>
            <span className="eyebrow">Rewizja geometrii</span>
            <h2 id="operational-review-geometry-title">
              Ustaw granice siatki symboli 5 × 3
            </h2>
            <p>
              Cztery numerowane punkty oznaczają zewnętrzne narożniki siatki
              symboli, nie czerwonej ramki. Plansza ucięta krawędzią zdjęcia
              jest „niepełna”: brakujące pola trafią do Weryfikacji symboli jako
              „Nierozpoznany ?”.
            </p>
          </div>
          <button
            aria-label="Zamknij edytor siatki"
            onClick={closeEditor}
            type="button"
          >
            ×
          </button>
        </header>
        {conflict ? (
          <p className="operationalReviewSaveError" role="alert">
            {conflict}
          </p>
        ) : null}
        {open ? (
          <BoardGeometryCorrectionEditor
            canvasLabel="Pojedynczy layout z edytowalną siatką"
            key={target.key}
            onConflict={handleConflict}
            onSaved={handleSaved}
            saveLabel="Zapisz nową rewizję"
            target={target}
          />
        ) : null}
      </dialog>
    </>
  );
}
