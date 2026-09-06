'use client';

import type { ImageGridReviewPageResponse } from '@game-predictor/admin-api-client';
import { useRef, useState } from 'react';
import type { ImageFolderImportClient } from './image-folder-import-actions';
import { startLocalReviewerProcess } from '../reviewer-access/reviewer-local-start';
import {
  buildPreparedLocalReviewUrl,
  prepareLocalReviewerWindow,
  navigatePreparedLocalReviewerWindow,
  closePreparedLocalReviewerWindow,
} from '../reviewer-access/reviewer-local-window';

export function ImportGeometryReviewSummary({
  api,
  gameId,
  jobId,
}: {
  readonly api: ImageFolderImportClient;
  readonly gameId: string;
  readonly jobId: string;
}) {
  const [counts, setCounts] = useState<
    ImageGridReviewPageResponse['counts'] | null
  >(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);

  async function refresh() {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await api.listImageGridReviews({
        gameId,
        importJobId: jobId,
        limit: 1,
        view: 'all',
      });
      if (!result.data || result.error) throw new Error();
      setCounts(result.data.counts);
    } catch {
      setError('Nie udało się odczytać liczby siatek.');
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  async function correct() {
    if (lock.current) return;
    const input = { gameId, importJobId: jobId };
    const base = buildPreparedLocalReviewUrl(window.location.href, input);
    if (!base) {
      setError('Korekta jest dostępna tylko w lokalnym Adminie.');
      return;
    }
    const url = new URL(base);
    url.searchParams.set('gridView', 'needs_correction');
    const popup = prepareLocalReviewerWindow(
      window.location.href,
      input,
      (url, target) => window.open(url, target),
    );
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await startLocalReviewerProcess(api);
      if (!result.ok) {
        closePreparedLocalReviewerWindow(popup);
        setError(result.error);
        return;
      }
      if (
        !popup ||
        !navigatePreparedLocalReviewerWindow(popup, url.toString())
      ) {
        setError(
          'Przeglądarka zablokowała otwarcie Reviewera. Zezwól na nowe okno i spróbuj ponownie.',
        );
      }
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  return (
    <details
      onToggle={(event) => {
        if (event.currentTarget.open) void refresh();
      }}
    >
      <summary>Siatki i ręczna korekta</summary>
      {counts ? (
        <p>
          Gotowe siatki: {counts.approved + counts.needsValidation} · do
          ręcznego ustawienia: {counts.needsCorrection}
        </p>
      ) : null}
      <button
        type="button"
        className="secondaryButton"
        disabled={busy}
        onClick={() => void refresh()}
      >
        Odśwież liczniki siatek
      </button>
      <button
        type="button"
        className="secondaryButton"
        disabled={busy}
        onClick={() => void correct()}
      >
        Popraw siatki
      </button>
      {error ? <p role="alert">{error}</p> : null}
    </details>
  );
}
