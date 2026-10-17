'use client';

import type {
  createAdminApiClient,
  HistoricalAcceptanceResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useRef, useState } from 'react';

export type HistoricalAcceptanceClient = Pick<
  ReturnType<typeof createAdminApiClient>,
  | 'createHistoricalGridAcceptance'
  | 'previewHistoricalGridAcceptanceNext'
  | 'confirmHistoricalGridAcceptance'
  | 'runHistoricalGridAcceptanceNext'
  | 'getHistoricalGridAcceptance'
>;

const PHASE_LABELS = {
  previewing: 'Przygotowanie podglądu',
  previewed: 'Podgląd gotowy do potwierdzenia',
  running: 'Przebieg w toku',
  done: 'Przebieg zakończony',
};

function reasonLabel(reason: string) {
  if (reason.includes('ALREADY_ACCEPTED'))
    return 'Rewizja została już zaakceptowana';
  if (reason.includes('MIXED') || reason.includes('REVISION_CONFLICT'))
    return 'Konflikt bieżącej rewizji geometrii';
  if (
    reason.includes('MODEL') ||
    reason.includes('PROVENANCE') ||
    reason.includes('EVIDENCE')
  )
    return 'Brak zgodnego oryginalnego dowodu modelu';
  if (reason.includes('POSITION') || reason.includes('GEOMETRY_MISSING'))
    return 'Niepełny lub niejednoznaczny zestaw pozycji';
  if (reason.includes('PARTIAL')) return 'Częściowa plansza';
  if (reason.includes('DEFERRED')) return 'Odroczona pozycja';
  if (reason.includes('GRID_ISSUE'))
    return 'Aktualne zgłoszenie błędnej siatki';
  if (reason.includes('OWNER') || reason.includes('PROJECTION'))
    return 'Niepewne przypisanie lub brak istniejącej projekcji';
  if (reason.includes('OPERATOR_EXCEPTION'))
    return 'Zdjęcie ma zachowany wyjątek operatora';
  if (reason.includes('GEOMETRY')) return 'Niezgodna geometria';
  return 'Rewizja nie spełnia warunków akceptacji';
}

type SavedOperation = {
  createKey: string;
  operationId?: string;
  confirmKey?: string;
  runKey?: string;
  runCursor?: number;
};

export function HistoricalGridAcceptanceControl({
  api,
  gameId,
}: {
  readonly api: HistoricalAcceptanceClient;
  readonly gameId: string;
}) {
  const [report, setReport] = useState<HistoricalAcceptanceResponse | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const request = useRef(0);
  const saved = useRef<SavedOperation | null>(null);
  const storageKey = `historical-grid-acceptance-v1:${gameId}`;
  useEffect(
    () => () => {
      request.current += 1;
    },
    [],
  );

  function save(value: SavedOperation) {
    // Save transport identities before the request, including an unanswered create.
    localStorage.setItem(storageKey, JSON.stringify(value));
    saved.current = value;
  }

  function checked(result: {
    data?: HistoricalAcceptanceResponse;
    error?: unknown;
  }) {
    if (
      result.error ||
      !result.data ||
      result.data.gameId !== gameId ||
      (saved.current?.operationId &&
        result.data.operationId !== saved.current.operationId)
    ) {
      throw new Error(
        'Operacja nie powiodła się. Wznów zapisany zakres; nie twórz nowego podglądu.',
      );
    }
    return result.data;
  }

  async function drive(initial: HistoricalAcceptanceResponse, id: number) {
    let current = initial;
    setReport(current);
    // Every response is durable. Stop/reload preserves the operation and cursor.
    while (
      request.current === id &&
      ['previewing', 'running'].includes(current.phase) &&
      current.preparationState !== 'HISTORICAL_EVIDENCE_VERIFICATION_TIME_LIMIT'
    ) {
      if (current.phase === 'previewing') {
        current = checked(
          await api.previewHistoricalGridAcceptanceNext(
            gameId,
            current.operationId,
            {
              expectedCursor: current.previewCursor,
            },
          ),
        );
      } else {
        const state = saved.current;
        if (!state) throw new Error('Brak zapisanej operacji.');
        const runKey =
          state.runCursor === current.runCursor && state.runKey
            ? state.runKey
            : crypto.randomUUID();
        save({ ...state, runKey, runCursor: current.runCursor });
        current = checked(
          await api.runHistoricalGridAcceptanceNext(
            gameId,
            current.operationId,
            {
              expectedCursor: current.runCursor,
              idempotencyKey: runKey,
            },
          ),
        );
      }
      if (request.current !== id) return;
      setReport(current);
    }
  }

  async function perform(kind: 'create' | 'resume' | 'confirm') {
    const id = ++request.current;
    setBusy(true);
    setError(null);
    try {
      let current: HistoricalAcceptanceResponse;
      if (kind === 'create') {
        save({ createKey: crypto.randomUUID() });
        current = checked(
          await api.createHistoricalGridAcceptance(gameId, {
            idempotencyKey: saved.current!.createKey,
          }),
        );
        save({ ...saved.current!, operationId: current.operationId });
      } else if (kind === 'resume') {
        const raw = localStorage.getItem(storageKey);
        if (!raw) throw new Error('Brak zapisanej operacji dla tej gry.');
        const state: SavedOperation = JSON.parse(raw);
        if (!state.createKey)
          throw new Error('Zapis operacji jest nieprawidłowy.');
        saved.current = state;
        current = checked(
          state.operationId
            ? await api.getHistoricalGridAcceptance(gameId, state.operationId)
            : await api.createHistoricalGridAcceptance(gameId, {
                idempotencyKey: state.createKey,
              }),
        );
        save({ ...state, operationId: current.operationId });
      } else {
        if (!report || !confirmed || !saved.current) return;
        const confirmKey = saved.current.confirmKey ?? crypto.randomUUID();
        save({ ...saved.current, confirmKey });
        current = checked(
          await api.confirmHistoricalGridAcceptance(
            gameId,
            report.operationId,
            {
              idempotencyKey: confirmKey,
              confirmed: true,
            },
          ),
        );
      }
      if (request.current === id) await drive(current, id);
    } catch (failure) {
      if (request.current === id)
        setError(
          failure instanceof Error
            ? failure.message
            : 'Nie udało się odczytać operacji.',
        );
    } finally {
      if (request.current === id) setBusy(false);
    }
  }

  return (
    <section aria-label="Historyczna akceptacja siatek" aria-busy={busy}>
      <h4>Historyczna akceptacja siatek</h4>
      <p>
        Zmiana statusów zgodnych rewizji. Bez ponownego cięcia, modelu i nowych
        komórek. Decyzje człowieka pozostają zachowane.
      </p>
      <button
        type="button"
        className="secondaryButton"
        disabled={busy || (report !== null && report.phase !== 'done')}
        onClick={() => void perform('create')}
      >
        Przygotuj podgląd tej gry
      </button>
      <button
        type="button"
        className="secondaryButton"
        disabled={busy}
        onClick={() => void perform('resume')}
      >
        Wznów zapisaną operację
      </button>
      {busy ? (
        <button
          type="button"
          className="secondaryButton"
          onClick={() => {
            request.current += 1;
            setBusy(false);
          }}
        >
          Przerwij oczekiwanie
        </button>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
      {report ? (
        <>
          {report.preparationState === 'HISTORICAL_EVIDENCE_PREPARING' ? (
            <p>Przygotowanie dowodów. Postęp jest zapisywany.</p>
          ) : null}
          {report.preparationState ===
          'HISTORICAL_EVIDENCE_VERIFICATION_TIME_LIMIT' ? (
            <p role="alert">
              Weryfikacja pliku nie ukończyła się w 30 sekund. Postęp indeksu
              pozostaje zapisany. Wznów po sprawdzeniu dostępności dysku. Zakres
              nie został zaakceptowany.
            </p>
          ) : null}
          <p>
            Operacja: {report.operationId}. Stan: {PHASE_LABELS[report.phase]}.
            Zdjęcia: {report.sourceCount}. Rewizje: {report.revisionCount}.
          </p>
          <p>
            Kwalifikujące się zdjęcia: {report.eligibleCount}. Zaakceptowane:{' '}
            {report.acceptedCount}. Pominięte w przebiegu: {report.skippedCount}
            .
          </p>
          <p>
            Podgląd: {report.previewCursor}. Przebieg: {report.runCursor}.
            Powody mogą dotyczyć tego samego zdjęcia; nie sumuj ich.
          </p>
          <ul>
            {Object.entries(
              report.phase === 'running' || report.phase === 'done'
                ? report.runReasons
                : report.previewReasons,
            ).map(([reason, count]) => (
              <li key={reason}>
                {reasonLabel(reason)}: {count} zdjęć
              </li>
            ))}
          </ul>
          {report.phase === 'previewed' ? (
            <>
              <label>
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={busy}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                Potwierdzam zmianę wyłącznie statusów w tym zamrożonym zakresie
                tej gry.
              </label>
              <button
                type="button"
                disabled={busy || !confirmed}
                onClick={() => void perform('confirm')}
              >
                Zatwierdź i uruchom przebieg
              </button>
            </>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
