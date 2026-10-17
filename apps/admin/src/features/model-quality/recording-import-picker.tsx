'use client';

import type {
  AdminApiClient,
  JobResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useState } from 'react';

import { recordingImportLabel } from './recording-groups-state';

const READ_LIMIT = 200;
const PAGE_SIZE = 20;

export function RecordingImportPicker({
  api,
  gameId,
  value,
  disabled,
  onChange,
  onLoaded,
}: {
  readonly api: Pick<AdminApiClient, 'listJobs'>;
  readonly gameId: string;
  readonly value: string;
  readonly disabled: boolean;
  readonly onChange: (id: string) => void;
  readonly onLoaded: (jobs: JobResponse[]) => void;
}) {
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [filter, setFilter] = useState('');
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [limited, setLimited] = useState(false);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(async () => {
      if (cancelled) return;
      setLoading(true);
      setError('');
      try {
        const result = await api.listJobs({
          gameId,
          jobType: 'import',
          limit: READ_LIMIT,
        });
        if (cancelled) return;
        if (result.data === undefined)
          throw new Error('Nie udało się pobrać importów tej gry.');
        const ownJobs = result.data.filter(
          (job) => job.gameId === gameId && job.jobType === 'import',
        );
        setLimited(ownJobs.length >= READ_LIMIT);
        const imageJobs = ownJobs.filter(
          (job) =>
            'importKind' in job.inputPayload &&
            job.inputPayload.importKind === 'image_directory',
        );
        setJobs(imageJobs);
        onLoaded(imageJobs);
        setPage(0);
      } catch {
        if (!cancelled)
          setError('Nie udało się pobrać importów tej gry. Ponów odczyt.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, gameId, refresh, onLoaded]);

  const filtered = jobs.filter((job) =>
    recordingImportLabel(job)
      .toLocaleLowerCase('pl-PL')
      .includes(filter.toLocaleLowerCase('pl-PL').trim()),
  );
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(
    currentPage * PAGE_SIZE,
    (currentPage + 1) * PAGE_SIZE,
  );
  const selected = jobs.find((job) => job.id === value);
  return (
    <section aria-label="Wybór importu nagrania">
      <p>
        Wybierz import obejmujący całe nagranie. Nazwa katalogu pomaga w
        wyborze; nie potwierdza niezależności.
      </p>
      {loading ? <p aria-busy="true">Odczytywanie importów tej gry…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      <button
        type="button"
        disabled={disabled || loading}
        onClick={() => setRefresh((current) => current + 1)}
      >
        Odśwież listę importów
      </button>
      <label>
        Filtr nazwy lub daty importu
        <input
          value={filter}
          disabled={disabled || loading}
          onChange={(event) => {
            setFilter(event.target.value);
            setPage(0);
          }}
        />
      </label>
      <label>
        Import nagrania
        <select
          aria-label="Import nagrania"
          value={value}
          disabled={disabled || loading || !!error}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Wybierz import tej gry</option>
          {selected && !visible.some((job) => job.id === selected.id) ? (
            <option value={selected.id}>
              {recordingImportLabel(selected)} · wybrany
            </option>
          ) : null}
          {visible.map((job) => (
            <option key={job.id} value={job.id}>
              {recordingImportLabel(job)}
            </option>
          ))}
        </select>
      </label>
      {!loading && !error ? (
        <>
          {filtered.length === 0 ? (
            <p>
              {jobs.length === 0
                ? 'Brak importów zdjęć tej gry.'
                : 'Brak importów pasujących do filtra.'}
            </p>
          ) : (
            <p>
              Strona importów {currentPage + 1} z {pageCount}. Wyświetlono{' '}
              {visible.length} z {filtered.length} pobranych importów.
            </p>
          )}
          {pageCount > 1 ? (
            <div className="buttonRow">
              <button
                type="button"
                disabled={disabled || currentPage === 0}
                onClick={() => setPage(currentPage - 1)}
              >
                Poprzednia strona importów
              </button>
              <button
                type="button"
                disabled={disabled || currentPage + 1 >= pageCount}
                onClick={() => setPage(currentPage + 1)}
              >
                Następna strona importów
              </button>
            </div>
          ) : null}
          {limited ? (
            <p>
              Odczyt ograniczono do 200 ostatnich importów tej gry. Starsza
              historia nie jest tutaj kompletna. Filtr przeszukuje tylko pobraną
              listę.
            </p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
