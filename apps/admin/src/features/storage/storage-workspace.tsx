'use client';

import type {
  ImageStorageInventoryResponse,
  StorageGcPreviewResponse,
  StorageGcRunResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import styles from './storage-workspace.module.css';

const TERMINAL = new Set(['completed', 'failed', 'cancelled']);

export function StorageWorkspace({
  apiBaseUrl,
}: {
  readonly apiBaseUrl: string;
}) {
  const api = useMemo(
    () => createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl],
  );
  const [inventory, setInventory] =
    useState<ImageStorageInventoryResponse | null>(null);
  const [preview, setPreview] = useState<StorageGcPreviewResponse | null>(null);
  const [run, setRun] = useState<StorageGcRunResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollActive = useRef(false);

  const loadInventory = useCallback(async () => {
    setError(null);
    const result = await api.getImageStorageInventory();
    if (result.error !== undefined || result.data === undefined) {
      setError('Nie udało się odświeżyć inwentarza pamięci.');
      return;
    }
    setInventory(result.data);
  }, [api]);

  useEffect(() => void loadInventory(), [loadInventory]);

  async function refresh() {
    setBusy(true);
    setError(null);
    const result = await api.refreshImageStorageInventory();
    if (result.error !== undefined || result.data === undefined) {
      setBusy(false);
      setError('Nie udało się uruchomić pomiaru pamięci.');
      return;
    }
    const jobId = result.data.id;
    for (let attempt = 0; attempt < 120; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      const status = await api.getJob(jobId);
      if (status.data?.status === 'completed') {
        await loadInventory();
        setBusy(false);
        return;
      }
      if (status.data !== undefined && TERMINAL.has(status.data.status)) break;
    }
    setBusy(false);
    setError('Pomiar nie zakończył się poprawnie. Sprawdź job inwentarza.');
  }

  useEffect(() => {
    if (run?.jobId == null || TERMINAL.has(run.status) || pollActive.current)
      return;
    const timer = window.setInterval(() => {
      if (pollActive.current) return;
      pollActive.current = true;
      void api.getStorageGcRun(run.id).then((result) => {
        pollActive.current = false;
        if (result.data !== undefined) setRun(result.data);
      });
    }, 2000);
    return () => window.clearInterval(timer);
  }, [api, run]);

  async function preparePreview() {
    setBusy(true);
    setError(null);
    const result = await api.createStorageGcPreview();
    setBusy(false);
    if (result.error !== undefined || result.data === undefined) {
      setError('Nie udało się przygotować bezpiecznego raportu czyszczenia.');
      return;
    }
    setPreview(result.data);
  }

  async function startCleanup() {
    if (preview === null) return;
    setBusy(true);
    setError(null);
    const result = await api.startStorageGcRun({
      confirmed: true,
      manifestChecksumSha256: preview.manifestChecksumSha256,
      previewId: preview.id,
      previewToken: preview.previewToken,
    });
    setBusy(false);
    if (result.error !== undefined || result.data === undefined) {
      setError('Raport wygasł albo dane zmieniły się. Przygotuj nowy raport.');
      return;
    }
    setRun(result.data);
    setPreview(null);
  }

  return (
    <section aria-label="Pamięć i czyszczenie" className={styles.workspace}>
      <header className={styles.header}>
        <div>
          <p className="eyebrow">Kontrola przestrzeni</p>
          <h1>Pamięć i czyszczenie</h1>
        </div>
        <button
          className="secondaryButton"
          disabled={busy}
          onClick={() => void refresh()}
          type="button"
        >
          {busy ? 'Mierzenie…' : 'Odśwież inwentarz'}
        </button>
      </header>
      {error === null ? null : (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {inventory === null ? (
        <p className={styles.muted}>Ładowanie inwentarza…</p>
      ) : (
        <>
          <div className={styles.metrics}>
            <article>
              <span>Łącznie</span>
              <strong>{formatBytes(inventory.totalSizeBytes)}</strong>
              <small>
                {inventory.totalFileCount.toLocaleString('pl-PL')} plików
              </small>
            </article>
            <article>
              <span>Automatyczne usuwanie</span>
              <strong>
                {inventory.automaticDeletion ? 'Włączone' : 'Tryb obserwacji'}
              </strong>
              <small>Chronione dane nigdy nie są wybieralne</small>
            </article>
            {inventory.volumes.map((volume) => {
              const pressure = pressureState(volume.freeBytes);
              return (
                <article key={volume.key}>
                  <span>Wolumin {volume.key.toUpperCase()}</span>
                  <strong>{formatBytes(volume.freeBytes)} wolne</strong>
                  <small>
                    {formatBytes(volume.totalBytes)} łącznie ·{' '}
                    {volume.roots.join(' + ')}
                  </small>
                  <em className={styles[pressure.className]}>
                    {pressure.label}
                  </em>
                </article>
              );
            })}
            <article>
              <span>PostgreSQL</span>
              <strong>
                {inventory.databaseSizeBytes === null
                  ? 'Brak pomiaru'
                  : formatBytes(inventory.databaseSizeBytes)}
              </strong>
              <small>
                Pomiar: {new Date(inventory.measuredAt).toLocaleString('pl-PL')}
              </small>
            </article>
          </div>
          <div className={styles.namespaces}>
            {inventory.namespaces.map((item) => (
              <article key={item.name}>
                <div>
                  <strong>{label(item.name)}</strong>
                  <span
                    className={
                      item.protected ? styles.protected : styles.derived
                    }
                  >
                    {item.protected ? 'chronione' : 'odtwarzalne'}
                  </span>
                </div>
                <b>{formatBytes(item.sizeBytes)}</b>
                <small>
                  {item.fileCount.toLocaleString('pl-PL')} plików ·{' '}
                  {item.retentionPolicy}
                </small>
              </article>
            ))}
          </div>
        </>
      )}
      <footer className={styles.actions}>
        <p>
          Usunięcie cache roboczego może wydłużyć pierwszy historyczny retry.
          Oryginały, cropy z referencjami i modele są chronione.
        </p>
        <button
          className="primaryButton"
          disabled={busy}
          onClick={() => void preparePreview()}
          type="button"
        >
          Przygotuj raport czyszczenia
        </button>
      </footer>
      {run === null ? null : (
        <section className={styles.run}>
          <strong>Garbage collector · {run.status}</strong>
          <span>
            {run.deletedCount}/{run.candidateCount} · odzyskano{' '}
            {formatBytes(run.deletedBytes)}
          </span>
        </section>
      )}
      {preview === null ? null : (
        <div aria-modal="true" className={styles.backdrop} role="dialog">
          <section className={styles.modal}>
            <p className="eyebrow">Dry-run · {preview.policyVersion}</p>
            <h2>Bezpieczne dane do usunięcia</h2>
            <dl>
              <div>
                <dt>Kandydaci</dt>
                <dd>{preview.candidateCount.toLocaleString('pl-PL')}</dd>
              </div>
              <div>
                <dt>Do odzyskania</dt>
                <dd>{formatBytes(preview.candidateBytes)}</dd>
              </div>
              <div>
                <dt>Chronione</dt>
                <dd>
                  {preview.protectedCount.toLocaleString('pl-PL')} ·{' '}
                  {formatBytes(preview.protectedBytes)}
                </dd>
              </div>
              <div>
                <dt>Przewidywane wolne</dt>
                <dd>{formatBytes(preview.predictedFreeBytes)}</dd>
              </div>
            </dl>
            <h3>Kategorie kwalifikujące się</h3>
            {summaryRows(preview.categoryCounts).length === 0 ? (
              <p>Brak bezpiecznych kandydatów.</p>
            ) : (
              <ul>
                {summaryRows(preview.categoryCounts).map(([name, values]) => (
                  <li key={name}>
                    {label(name)}: {values.count.toLocaleString('pl-PL')} ·{' '}
                    {formatBytes(values.bytes)}
                  </li>
                ))}
              </ul>
            )}
            <h3>Blokady ochronne</h3>
            {summaryRows(preview.protectionReasonCounts).length === 0 ? (
              <p>Brak blokad.</p>
            ) : (
              <ul>
                {summaryRows(preview.protectionReasonCounts).map(
                  ([name, values]) => (
                    <li key={name}>
                      {name}: {values.count.toLocaleString('pl-PL')} ·{' '}
                      {formatBytes(values.bytes)}
                    </li>
                  ),
                )}
              </ul>
            )}
            <p>
              Operacja jest nieodwracalna. Przed każdą partią system ponownie
              sprawdzi ścieżkę, zależności i tożsamość pliku.
            </p>
            <div className={styles.modalActions}>
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => setPreview(null)}
                type="button"
              >
                Anuluj
              </button>
              <button
                className="dangerButton"
                disabled={busy || preview.candidateCount === 0}
                onClick={() => void startCleanup()}
                type="button"
              >
                Usuń bezpieczne dane
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

function formatBytes(value: number): string {
  const gib = value / 1024 ** 3;
  return gib >= 0.1
    ? `${gib.toLocaleString('pl-PL', { maximumFractionDigits: 2 })} GiB`
    : `${(value / 1024 ** 2).toLocaleString('pl-PL', { maximumFractionDigits: 1 })} MiB`;
}

function label(value: string): string {
  return (
    (
      {
        staging: 'Staging',
        originals: 'Oryginały',
        working: 'Dane robocze',
        crops: 'Cropy',
        training: 'Trening',
        models: 'Modele',
        exports: 'Eksporty',
      } as Record<string, string>
    )[value] ?? value
  );
}

function pressureState(freeBytes: number): {
  readonly className: 'safe' | 'warning' | 'gc' | 'blocked';
  readonly label: string;
} {
  const gib = freeBytes / 1024 ** 3;
  if (gib < 30) return { className: 'blocked', label: 'blokada zapisu' };
  if (gib < 60) return { className: 'gc', label: 'wymagane czyszczenie' };
  if (gib < 80) return { className: 'warning', label: 'ostrzeżenie' };
  return { className: 'safe', label: 'bezpiecznie' };
}

function summaryRows(
  values: Record<string, Record<string, number>>,
): [string, { bytes: number; count: number }][] {
  return Object.entries(values)
    .map(
      ([name, summary]) =>
        [name, { bytes: summary.bytes ?? 0, count: summary.count ?? 0 }] as [
          string,
          { bytes: number; count: number },
        ],
    )
    .sort(([left], [right]) => left.localeCompare(right));
}
