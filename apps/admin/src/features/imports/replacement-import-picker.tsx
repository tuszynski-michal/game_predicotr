'use client';

import { useEffect, useRef, useState } from 'react';
import type { ReplacementRepairManifest } from '@game-predictor/manual-image-selection-core/replacement-repair';
import { pickLocalDirectory } from '../../lib/local-directory-picker';
import {
  readReplacementRepair,
  readReplacementFilledGaps,
  readReplacementImportSelection,
} from '../manual-image-selection/replacement-repair-storage';
import { sha256Hex } from '../manual-image-selection/manual-image-selection-fsa-adapter';
import {
  uploadImageFolder,
  type ImageFolderImportClient,
} from './image-folder-import-actions';

export function ReplacementImportPicker({
  api,
  gameId,
  gameLabel,
  disabled,
  onReady,
}: {
  readonly api: ImageFolderImportClient;
  readonly gameId: string;
  readonly gameLabel: string;
  readonly disabled: boolean;
  readonly onReady: (uploadId: string) => Promise<void>;
}) {
  const [directory, setDirectory] = useState<FileSystemDirectoryHandle | null>(
    null,
  );
  const [manifest, setManifest] = useState<ReplacementRepairManifest | null>(
    null,
  );
  const [selected, setSelected] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [progress, setProgress] = useState('');
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  async function choose() {
    setBusy(true);
    setError('');
    setManifest(null);
    setSelected([]);
    setDirectory(null);
    try {
      const next = await pickLocalDirectory({
        id: 'gp-replacement-import',
        mode: 'read',
      });
      const value = await readReplacementRepair(next);
      if (!value || value.request.gameId !== gameId)
        throw new Error(
          'Wybierz folder gotowych zamienników dla bieżącej gry.',
        );
      await readReplacementFilledGaps(next);
      if (!mounted.current) return;
      setDirectory(next);
      setManifest(value);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? `Nie można otworzyć zamienników. ${cause.message} Sprawdź folder w przygotowaniu zamienników.`
          : 'Nie można otworzyć folderu. Wybierz go ponownie.',
      );
    } finally {
      setBusy(false);
    }
  }
  async function upload() {
    if (!directory || !selected.length) return;
    setBusy(true);
    setError('');
    setProgress('Sprawdzanie zapisanych plików…');
    try {
      const verified = await readReplacementImportSelection(
        directory,
        selected,
      );
      if (verified.selection.request.gameId !== gameId)
        throw new Error('Folder dotyczy innej gry.');
      const digest = await sha256Hex(
        new Blob([JSON.stringify(verified.selection)]),
      );
      const key = `replacement-upload:${gameId}:${digest}`;
      let command = localStorage.getItem(key);
      if (!command) {
        command = crypto.randomUUID();
        localStorage.setItem(key, command);
      }
      const result = await uploadImageFolder(
        api,
        verified.files,
        gameId,
        (uploaded, total) =>
          setProgress(`Przesłano ${uploaded} z ${total} zdjęć.`),
        { selection: verified.selection, idempotencyKey: command },
      );
      if (!result.ok) throw new Error(result.error);
      if (result.kind !== 'uploaded')
        throw new Error('Brak plików do importu.');
      setProgress(
        'Pliki są zapisane na serwerze. Przygotowanie raportu importu…',
      );
      if (!mounted.current) return;
      await onReady(result.uploadId);
      setProgress(
        'Gotowy folder jest dostępny poniżej. Import i sprawdzenie nowych plansz pozostają do wykonania.',
      );
    } catch (cause) {
      setError(
        `${cause instanceof Error ? cause.message : 'Przerwano połączenie.'} Wybierz te same wpisy i ponów przesyłanie — zapisany postęp zostanie odtworzony.`,
      );
    } finally {
      setBusy(false);
    }
  }
  const committed =
    manifest?.journal.filter((write) => write.state === 'committed') ?? [];
  return (
    <fieldset disabled={disabled || busy}>
      <legend>Przygotowane zamienniki — {gameLabel}</legend>
      <p>
        Wybierz folder zapisany podczas przygotowania zamienników. Przesłane
        zostaną tylko zaznaczone, sprawdzone zdjęcia.
      </p>
      <button type="button" onClick={() => void choose()}>
        Otwórz gotowe zamienniki
      </button>
      {manifest && committed.length === 0 && (
        <p>
          Brak gotowych zdjęć. Dokończ zapis zamiennika w przygotowaniu zdjęć.
        </p>
      )}
      {committed.map((write) => {
        const range = manifest!.request.allowedRanges.find(
          (item) => item.entryId === write.entryId,
        );
        return (
          <label key={write.id} style={{ display: 'block' }}>
            <input
              type="checkbox"
              checked={selected.includes(write.entryId)}
              onChange={(event) =>
                setSelected((current) =>
                  event.target.checked
                    ? [...current, write.entryId]
                    : current.filter((id) => id !== write.entryId),
                )
              }
            />
            Plansze {range?.sequenceStart}–{range?.sequenceEnd}:{' '}
            {write.fileName}
          </label>
        );
      })}
      {committed.length > 0 && (
        <button
          type="button"
          disabled={!selected.length}
          onClick={() => void upload()}
        >
          Prześlij wybrane zamienniki
        </button>
      )}
      {busy && <p role="status">{progress || 'Sprawdzanie folderu…'}</p>}
      {!busy && progress && <p role="status">{progress}</p>}
      {error && <p role="alert">{error}</p>}
    </fieldset>
  );
}
