'use client';

import type {
  QualityMeasurementResponse,
  QualityMeasurementSummary,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import {
  clearMeasurementCommand,
  discardMeasurementCommand,
  readMeasurementCommand,
  saveMeasurementCommand,
  type MeasurementCommand,
} from './grid-quality-measurement-command';
import { GridQualityMeasurementMember } from './grid-quality-measurement-member';
import { GridQualityMeasurementReport } from './grid-quality-measurement-report';
import {
  measurementHardSources,
  type GridQualityMeasurementClient,
} from './grid-quality-measurement-state';

type PanelProps = {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly client?: GridQualityMeasurementClient;
};

/** Game/API keyed lifetime prevents a late response from crossing game boundaries. */
export function GridQualityMeasurementPanel(props: PanelProps) {
  return (
    <MeasurementPanel key={`${props.apiBaseUrl}:${props.gameId}`} {...props} />
  );
}

function MeasurementPanel({ apiBaseUrl, gameId, client }: PanelProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [items, setItems] = useState<QualityMeasurementSummary[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [selected, setSelected] = useState('');
  const [measurement, setMeasurement] =
    useState<QualityMeasurementResponse | null>(null);
  const [seed, setSeed] = useState('');
  const [sampleSize, setSampleSize] = useState('100');
  const [hard, setHard] = useState('');
  const [pending, setPending] = useState<MeasurementCommand | null>(null);
  const [corrupt, setCorrupt] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const alive = useRef(true);
  const listRequest = useRef(0),
    detailRequest = useRef(0);
  const mutationLock = useRef(false);
  const selection = useRef('');
  const invalidateReads = useCallback(() => {
    ++listRequest.current;
    ++detailRequest.current;
  }, []);

  const readPending = useCallback(() => {
    try {
      setPending(readMeasurementCommand(localStorage, apiBaseUrl, gameId));
      setCorrupt(false);
    } catch (e) {
      setCorrupt(true);
      setError(
        e instanceof Error
          ? e.message
          : 'Nie można odczytać zapisanego polecenia.',
      );
    }
  }, [apiBaseUrl, gameId]);

  const loadList = useCallback(
    async (next?: string) => {
      const request = ++listRequest.current;
      setLoading(true);
      try {
        const result = await api.listGridQualityMeasurements(gameId, {
          limit: 20,
          ...(next ? { cursor: next } : {}),
        });
        if (!alive.current || request !== listRequest.current) return;
        if (!result.data) {
          setError(
            apiErrorMessage(result.error, 'Nie udało się odczytać pomiarów.'),
          );
          return;
        }
        setItems((old) =>
          next
            ? [
                ...old,
                ...result.data!.items.filter(
                  (item) =>
                    !old.some((v) => v.measurementId === item.measurementId),
                ),
              ]
            : result.data!.items,
        );
        setCursor(result.data.nextCursor);
      } catch {
        if (alive.current && request === listRequest.current)
          setError('Nie udało się odczytać pomiarów.');
      } finally {
        if (alive.current && request === listRequest.current) setLoading(false);
      }
    },
    [api, gameId],
  );

  const loadDetail = useCallback(
    async (id: string) => {
      const request = ++detailRequest.current;
      selection.current = id;
      setSelected(id);
      setMeasurement(null);
      if (!id) return;
      try {
        const result = await api.getGridQualityMeasurement(gameId, id);
        if (
          !alive.current ||
          request !== detailRequest.current ||
          selection.current !== id
        )
          return;
        if (!result.data) {
          setError(
            apiErrorMessage(result.error, 'Nie udało się odczytać pomiaru.'),
          );
          return;
        }
        if (result.data.gameId !== gameId || result.data.measurementId !== id) {
          setError('Odpowiedź pomiaru ma inny zakres.');
          return;
        }
        setMeasurement(result.data);
      } catch {
        if (alive.current && request === detailRequest.current)
          setError('Nie udało się odczytać pomiaru.');
      }
    },
    [api, gameId],
  );

  useEffect(() => {
    alive.current = true;
    queueMicrotask(() => {
      if (alive.current) {
        readPending();
        void loadList();
      }
    });
    return () => {
      alive.current = false;
      invalidateReads();
    };
  }, [invalidateReads, loadList, readPending]);

  async function send(command: MeasurementCommand, retry = false) {
    if (mutationLock.current || (!retry && (pending || corrupt))) return;
    mutationLock.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    const selectedAtStart = selection.current;
    try {
      if (!retry)
        saveMeasurementCommand(localStorage, apiBaseUrl, gameId, command);
      if (alive.current) setPending(command);
      const result =
        command.kind === 'capture'
          ? await api.captureGridQualityMeasurement(gameId, command.body)
          : command.kind === 'assess'
            ? await api.assessGridQualityMeasurement(
                gameId,
                command.measurementId,
                command.body,
              )
            : await api.approveOperationalGeometry(
                command.reviewItemId,
                { gameId, importJobId: command.importJobId },
                command.body,
              );
      if (!result.data) {
        if (alive.current)
          setError(
            apiErrorMessage(
              result.error,
              'Nie potwierdzono zapisu. Ponów dokładnie zapisane polecenie.',
            ),
          );
        return;
      }
      clearMeasurementCommand(localStorage, apiBaseUrl, gameId, command);
      if (!alive.current) return;
      setPending(null);
      setNotice(
        'Polecenie rozliczone. Aktualny stan pochodzi z ponownego odczytu.',
      );
      void loadList();
      // A response to an old selection never replaces the newly selected detail.
      if (selection.current === selectedAtStart) {
        const captured = 'current' in result.data ? result.data.current : null;
        const id =
          command.kind === 'capture' &&
          captured &&
          typeof captured === 'object' &&
          'measurementId' in captured
            ? String(captured.measurementId)
            : selection.current;
        if (id) void loadDetail(id);
      }
    } catch (e) {
      if (alive.current) {
        readPending();
        setError(
          e instanceof Error
            ? e.message
            : 'Nie potwierdzono zapisu. Zachowano polecenie do ponowienia.',
        );
      }
    } finally {
      mutationLock.current = false;
      if (alive.current) setBusy(false);
    }
  }

  function capture() {
    try {
      const size = Number(sampleSize);
      if (
        !Number.isInteger(size) ||
        size < 1 ||
        size > 100 ||
        !seed.trim() ||
        seed.length > 200
      )
        throw new Error(
          'Podaj seed (1–200 znaków) i rozmiar losowej próby 1–100.',
        );
      const hardSourceIds = measurementHardSources(hard);
      void send({
        kind: 'capture',
        body: {
          idempotencyKey: crypto.randomUUID(),
          seed,
          sampleSize: size,
          hardSourceIds,
        },
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Nieprawidłowe dane próby.');
    }
  }

  return (
    <section
      aria-label="Pomiar jakości geometrii V3"
      className="modelQualityWorkflowGroup"
    >
      <h3>Losowa kontrola jakości</h3>
      <p>
        Zamroź próbę, następnie jawnie oceń każde zdjęcie. Utworzenie próby nie
        uruchamia rozpoznawania ani treningu.
      </p>
      <fieldset disabled={busy || !!pending || corrupt}>
        <legend>Nowy pomiar</legend>
        <label>
          Seed{' '}
          <input
            aria-label="Seed próby"
            maxLength={200}
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
          />
        </label>
        <label>
          Liczba losowych zdjęć (1–100){' '}
          <input
            aria-label="Rozmiar próby"
            type="number"
            min={1}
            max={100}
            value={sampleSize}
            onChange={(e) => setSampleSize(e.target.value)}
          />
        </label>
        <details>
          <summary>Zaawansowane: trudne przykłady (opcjonalnie)</summary>
          <label>
            Trudne przykłady: własne UUID zdjęć, opcjonalnie{' '}
            <textarea
              aria-label="Trudne przykłady UUID"
              value={hard}
              onChange={(e) => setHard(e.target.value)}
            />
          </label>
        </details>
        <button type="button" onClick={capture}>
          Zamroź nową próbę
        </button>
      </fieldset>
      {pending || corrupt ? (
        <aside aria-label="Zapisane polecenie">
          <p>
            {corrupt
              ? 'Uszkodzony zapis polecenia. Automatyczne ponowienie jest zablokowane.'
              : `Zachowane polecenie: ${pending?.kind}. Odświeżenie strony wykonuje tylko odczyt.`}
          </p>
          <button
            type="button"
            disabled={busy || corrupt || !pending}
            onClick={() => {
              if (pending) void send(pending, true);
            }}
          >
            Ponów zapisane polecenie
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              try {
                discardMeasurementCommand(
                  localStorage,
                  apiBaseUrl,
                  gameId,
                  window.confirm(
                    'Zarchiwizować i porzucić zapisane polecenie? Mogło już zostać wykonane. Historia serwera pozostanie zachowana.',
                  ),
                );
                readPending();
              } catch {
                setError(
                  'Nie udało się zarchiwizować polecenia. Zachowano zapis.',
                );
              }
            }}
          >
            Zarchiwizuj i porzuć polecenie
          </button>
        </aside>
      ) : null}
      <button
        type="button"
        disabled={loading}
        onClick={() => {
          setError('');
          void loadList();
          if (selected) void loadDetail(selected);
        }}
      >
        Odśwież pomiary
      </button>
      {loading ? (
        <p role="status">Odczyt pomiarów…</p>
      ) : !items.length ? (
        <p>Brak zapisanych pomiarów.</p>
      ) : null}
      <label>
        Pomiar{' '}
        <select
          aria-label="Wybierz pomiar"
          value={selected}
          onChange={(e) => {
            setError('');
            void loadDetail(e.target.value);
          }}
        >
          <option value="">Wybierz…</option>
          {items.map((item) => (
            <option key={item.measurementId} value={item.measurementId}>
              {item.capturedAt} · {item.seed} · losowe {item.randomSampleCount},
              trudne {item.hardSampleCount}
            </option>
          ))}
        </select>
      </label>
      {cursor ? (
        <button
          type="button"
          disabled={loading}
          onClick={() => void loadList(cursor)}
        >
          Kolejne pomiary
        </button>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {selected && !measurement ? (
        <p>Oczekiwanie na szczegóły wybranego pomiaru.</p>
      ) : null}
      {measurement ? (
        <>
          {!measurement.manifestAvailable ? (
            <p role="alert">
              Manifest niedostępny: {measurement.manifestBlocker}. Zapis ocen i
              zatwierdzeń jest zablokowany.
            </p>
          ) : null}
          <GridQualityMeasurementReport measurement={measurement} />
          {measurement.members.map((member) => (
            <GridQualityMeasurementMember
              key={`${measurement.measurementId}:${member.sampleKind}:${member.sourceId}:${member.revision}`}
              member={member}
              measurement={measurement}
              apiBaseUrl={apiBaseUrl}
              disabled={
                busy || !!pending || corrupt || !measurement.manifestAvailable
              }
              onCommand={(command) => void send(command)}
            />
          ))}
        </>
      ) : null}
    </section>
  );
}
