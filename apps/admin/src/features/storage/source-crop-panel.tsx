'use client';

import type {
  GameResponse,
  SourceCropRunResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useId, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import { formatStorageBytes } from '../jobs/job-state.ts';
import {
  loadSourceCropRuns,
  planSourceCrop,
  refreshSourceCropRun,
  startSourceCrop,
  type SourceCropClient,
} from './source-crop-actions.ts';
import {
  EMPTY_SCOPE_DRAFT,
  buildScope,
  canStartRun,
  exclusionLabel,
  exclusionRows,
  isExecuting,
  isFinished,
  isPlanning,
  isStartable,
  needsPolling,
  outcomeLabel,
  outcomeRows,
  pickResumableRun,
  progressPercent,
  scopeLabel,
  selectableGames,
  shortChecksum,
  statusLabel,
  type ScopeDraft,
  type ScopeMode,
  type SourceCropKind,
} from './source-crop-state.ts';
import styles from './source-crop-panel.module.css';

const DEFAULT_POLL_INTERVAL_MS = 2000;

interface SectionCopy {
  readonly title: string;
  readonly intro: string;
  readonly planButton: string;
  readonly startButton: string;
  readonly confirmTitle: string;
  readonly confirmButton: string;
  readonly savedLabel: string;
}

const COPY: Record<SourceCropKind, SectionCopy> = {
  crop: {
    confirmButton: 'Potwierdź i uruchom przycinanie',
    confirmTitle: 'Uruchomić przycinanie zdjęć?',
    intro:
      'Przycina zarządzane oryginały do obszaru chronionych plansz. Oryginał zostaje na dysku do czasu osobnego kroku usunięcia.',
    planButton: 'Zaplanuj przycinanie',
    savedLabel: 'Zaoszczędzono',
    startButton: 'Uruchom przycinanie…',
    title: 'Przycinanie zdjęć',
  },
  original_deletion: {
    confirmButton: 'Tak, usuń oryginały bezpowrotnie',
    confirmTitle: 'Usunąć oryginały przyciętych zdjęć?',
    intro:
      'Osobny krok po przycinaniu: usuwa z dysku oryginały, których przycięty crop został zweryfikowany.',
    planButton: 'Zaplanuj usunięcie oryginałów',
    savedLabel: 'Zwolniono',
    startButton: 'Usuń oryginały…',
    title: 'Usuń oryginały przyciętych zdjęć',
  },
};

const SCOPE_MODES: readonly { value: ScopeMode; label: string }[] = [
  { label: 'Wszystkie gry', value: 'all' },
  { label: 'Jedna gra', value: 'game' },
  { label: 'Lista sum SHA-256', value: 'checksums' },
];

export function SourceCropPanel({
  apiBaseUrl,
  client,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
}: {
  readonly apiBaseUrl: string;
  readonly client?: SourceCropClient;
  readonly pollIntervalMs?: number;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [runs, setRuns] = useState<readonly SourceCropRunResponse[] | null>(
    null,
  );
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const loaded = await loadSourceCropRuns(api);
      let gameList: readonly GameResponse[] = [];
      try {
        const result = await api.listGames();
        if (result.data !== undefined) gameList = result.data;
      } catch {
        gameList = [];
      }
      if (!active) return;
      setGames(selectableGames(gameList));
      if (loaded.ok) {
        setRuns(loaded.runs);
      } else {
        setLoadError(loaded.error);
        setRuns([]);
      }
    })();
    return () => {
      active = false;
    };
  }, [api]);

  return (
    <section
      aria-label="Przycinanie zdjęć i usuwanie oryginałów"
      className={styles.panel}
    >
      {loadError === null ? null : (
        <p className={styles.error} role="alert">
          {loadError}
        </p>
      )}
      {runs === null ? (
        <p className={styles.muted}>Ładowanie przebiegów przycinania…</p>
      ) : (
        (['crop', 'original_deletion'] as const).map((kind) => (
          <SourceCropSection
            api={api}
            games={games}
            initialRun={pickResumableRun(runs, kind)}
            key={kind}
            kind={kind}
            pollIntervalMs={pollIntervalMs}
          />
        ))
      )}
    </section>
  );
}

function SourceCropSection({
  api,
  games,
  initialRun,
  kind,
  pollIntervalMs,
}: {
  readonly api: SourceCropClient;
  readonly games: readonly GameResponse[];
  readonly initialRun: SourceCropRunResponse | null;
  readonly kind: SourceCropKind;
  readonly pollIntervalMs: number;
}) {
  const copy = COPY[kind];
  const isDeletion = kind === 'original_deletion';
  const headingId = useId();
  const dialogTitleId = useId();
  const [draft, setDraft] = useState<ScopeDraft>(EMPTY_SCOPE_DRAFT);
  const [run, setRun] = useState<SourceCropRunResponse | null>(initialRun);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const polling = useRef(false);

  useEffect(() => {
    if (run === null || !needsPolling(run)) return;
    let active = true;
    const timer = window.setInterval(() => {
      if (polling.current) return;
      polling.current = true;
      void refreshSourceCropRun(api, run.id).then((result) => {
        polling.current = false;
        if (!active) return;
        if (result.ok) {
          setPollError(null);
          setRun(result.run);
        } else {
          setPollError(result.error);
        }
      });
    }, pollIntervalMs);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [api, pollIntervalMs, run]);

  const locked = busy || (run !== null && needsPolling(run));

  async function plan() {
    const scope = buildScope(draft);
    if (!scope.ok) {
      setError(scope.error);
      return;
    }
    setBusy(true);
    setError(null);
    setPollError(null);
    setConfirming(false);
    setAcknowledged(false);
    const result = await planSourceCrop(api, kind, scope.scope);
    setBusy(false);
    if (result.ok) {
      setRun(result.run);
    } else {
      setError(result.error);
    }
  }

  async function start() {
    if (run === null) return;
    setBusy(true);
    setError(null);
    const result = await startSourceCrop(api, run, acknowledged);
    setBusy(false);
    setConfirming(false);
    if (result.ok) {
      setRun(result.run);
      setAcknowledged(false);
    } else {
      setError(result.error);
    }
  }

  return (
    <section
      aria-labelledby={headingId}
      className={isDeletion ? styles.sectionDanger : styles.section}
    >
      <header className={styles.sectionHeader}>
        <div>
          <p className="eyebrow">
            {isDeletion ? 'Krok nieodwracalny' : 'Oszczędność miejsca'}
          </p>
          <h2 id={headingId}>{copy.title}</h2>
        </div>
        {run === null ? null : (
          <span className={styles.status} data-status={run.status}>
            {statusLabel(run.status)}
          </span>
        )}
      </header>
      <p className={styles.muted}>{copy.intro}</p>
      {isDeletion ? <IrreversibleWarning /> : null}

      <fieldset className={styles.scope} disabled={locked}>
        <legend>Zakres</legend>
        <div className={styles.modes}>
          {SCOPE_MODES.map((mode) => (
            <label key={mode.value}>
              <input
                checked={draft.mode === mode.value}
                name={`scope-${kind}`}
                onChange={() => setDraft({ ...draft, mode: mode.value })}
                type="radio"
              />
              {mode.label}
            </label>
          ))}
        </div>
        {draft.mode === 'game' ? (
          <label className={styles.field}>
            Gra
            <select
              aria-label="Gra"
              onChange={(event) =>
                setDraft({ ...draft, gameId: event.target.value })
              }
              value={draft.gameId}
            >
              <option value="">Wybierz grę…</option>
              {games.map((game) => (
                <option key={game.id} value={game.id}>
                  {game.name} ({game.code})
                </option>
              ))}
            </select>
          </label>
        ) : null}
        {draft.mode === 'checksums' ? (
          <label className={styles.field}>
            Sumy SHA-256 (po jednej w linii, najwyżej 500)
            <textarea
              aria-label="Sumy SHA-256"
              onChange={(event) =>
                setDraft({ ...draft, checksumsText: event.target.value })
              }
              rows={4}
              spellCheck={false}
              value={draft.checksumsText}
            />
          </label>
        ) : null}
        <label className={styles.field}>
          Limit oryginałów (opcjonalnie)
          <input
            aria-label="Limit oryginałów"
            inputMode="numeric"
            onChange={(event) =>
              setDraft({ ...draft, limitText: event.target.value })
            }
            placeholder="bez limitu"
            type="text"
            value={draft.limitText}
          />
        </label>
      </fieldset>

      <div className={styles.actions}>
        <button
          className="secondaryButton"
          disabled={locked}
          onClick={() => void plan()}
          type="button"
        >
          {busy && run === null ? 'Planowanie…' : copy.planButton}
        </button>
        <small className={styles.muted}>
          Nowy podgląd zastępuje niezaczęty podgląd. Jednocześnie działa jeden
          przebieg.
        </small>
      </div>

      {error === null ? null : (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      {pollError === null ? null : (
        <p className={styles.error} role="alert">
          {pollError}
        </p>
      )}

      {run === null ? null : (
        <RunDetails
          acknowledged={acknowledged}
          busy={busy}
          copy={copy}
          onAcknowledge={setAcknowledged}
          onRequestStart={() => setConfirming(true)}
          run={run}
        />
      )}

      {confirming && run !== null ? (
        <div aria-modal="true" className={styles.backdrop} role="dialog">
          <section aria-labelledby={dialogTitleId} className={styles.modal}>
            <p className="eyebrow">
              {isDeletion ? 'Brak odwrotu' : 'Potwierdź'}
            </p>
            <h2 id={dialogTitleId}>{copy.confirmTitle}</h2>
            {isDeletion ? <IrreversibleWarning /> : null}
            <p>
              {run.eligibleCount.toLocaleString('pl-PL')} oryginałów ·{' '}
              {formatStorageBytes(run.candidateBytes)}
              {' · '}
              {isDeletion ? 'do zwolnienia' : 'szacowana oszczędność'}{' '}
              {formatStorageBytes(run.estimatedSavedBytes)}
            </p>
            <div className={styles.modalActions}>
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => setConfirming(false)}
                type="button"
              >
                Anuluj
              </button>
              <button
                className={isDeletion ? 'dangerButton' : 'primaryButton'}
                disabled={busy || !canStartRun(run, acknowledged)}
                onClick={() => void start()}
                type="button"
              >
                {copy.confirmButton}
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

function IrreversibleWarning() {
  return (
    <div
      aria-label="Ostrzeżenie o nieodwracalności"
      className={styles.warning}
      role="note"
    >
      <strong>Brak kopii zdjęć — operacji nie można cofnąć.</strong>
      <span>
        Usunięte oryginały znikają z dysku bez kwarantanny i nie ma ich kopii
        zapasowej. Pozostaje wyłącznie przycięty crop.
      </span>
    </div>
  );
}

function RunDetails({
  acknowledged,
  busy,
  copy,
  onAcknowledge,
  onRequestStart,
  run,
}: {
  readonly acknowledged: boolean;
  readonly busy: boolean;
  readonly copy: SectionCopy;
  readonly onAcknowledge: (value: boolean) => void;
  readonly onRequestStart: () => void;
  readonly run: SourceCropRunResponse;
}) {
  const isDeletion = run.kind === 'original_deletion';
  const reasons = exclusionRows(run);
  const progressLabelId = useId();
  return (
    <div className={styles.run}>
      <p className={styles.muted}>Zakres: {scopeLabel(run.scope)}</p>

      {isPlanning(run) ? (
        <p role="status">
          Worker przygotowuje podgląd… (kwalifikacja oryginałów)
        </p>
      ) : null}

      {isStartable(run) ? (
        <>
          <h3>Podgląd</h3>
          <dl className={styles.stats}>
            <div>
              <dt>Kwalifikujące się</dt>
              <dd>{run.eligibleCount.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Wykluczone</dt>
              <dd>{run.excludedCount.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Rozmiar oryginałów</dt>
              <dd>{formatStorageBytes(run.candidateBytes)}</dd>
            </div>
            <div>
              <dt>{isDeletion ? 'Do zwolnienia' : 'Szacowana oszczędność'}</dt>
              <dd>{formatStorageBytes(run.estimatedSavedBytes)}</dd>
            </div>
          </dl>
          <h3>Powody wykluczenia</h3>
          {reasons.length === 0 ? (
            <p className={styles.muted}>Brak wykluczeń.</p>
          ) : (
            <ul className={styles.list}>
              {reasons.map(([code, count]) => (
                <li key={code}>
                  {exclusionLabel(code)}: {count.toLocaleString('pl-PL')}
                </li>
              ))}
            </ul>
          )}
          {isDeletion ? (
            <label className={styles.acknowledge}>
              <input
                checked={acknowledged}
                onChange={(event) => onAcknowledge(event.target.checked)}
                type="checkbox"
              />
              Rozumiem, że nie ma kopii zdjęć, a usunięcia oryginałów nie można
              cofnąć.
            </label>
          ) : null}
          <div className={styles.actions}>
            <button
              className={isDeletion ? 'dangerButton' : 'primaryButton'}
              disabled={busy || !canStartRun(run, acknowledged)}
              onClick={onRequestStart}
              type="button"
            >
              {copy.startButton}
            </button>
            {run.eligibleCount <= 0 ? (
              <small className={styles.muted}>
                Brak kwalifikujących się oryginałów — nie ma co uruchamiać.
              </small>
            ) : null}
          </div>
        </>
      ) : null}

      {isExecuting(run) || isFinished(run) ? (
        <>
          <h3>{isFinished(run) ? 'Wynik' : 'Postęp'}</h3>
          <div
            aria-labelledby={progressLabelId}
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={progressPercent(run)}
            className={styles.bar}
            role="progressbar"
          >
            <span style={{ width: `${progressPercent(run)}%` }} />
          </div>
          <p id={progressLabelId}>
            Przetworzono {run.processedCount.toLocaleString('pl-PL')} z{' '}
            {run.eligibleCount.toLocaleString('pl-PL')} ({progressPercent(run)}
            %)
          </p>
          <dl className={styles.stats}>
            <div>
              <dt>Powodzenia</dt>
              <dd>{run.succeededCount.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Pominięte</dt>
              <dd>{run.skippedCount.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Błędy</dt>
              <dd>{run.failedCount.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>{copy.savedLabel}</dt>
              <dd>{formatStorageBytes(run.savedBytes)}</dd>
            </div>
          </dl>
          <ul aria-label="Wyniki według rodzaju" className={styles.list}>
            {outcomeRows(run).map(([code, count]) => (
              <li data-outcome={code} key={code}>
                {outcomeLabel(code)}: {count.toLocaleString('pl-PL')}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {run.status === 'failed' || run.status === 'cancelled' ? (
        <p className={styles.error} role="alert">
          {run.status === 'failed'
            ? 'Przebieg zakończył się błędem'
            : 'Przebieg anulowany'}
          {run.errorCode === null ? '' : ` (${run.errorCode})`}
          {run.errorMessage === null ? '' : `: ${run.errorMessage}`}
        </p>
      ) : null}

      {run.failures.length === 0 ? null : (
        <>
          <h3>Błędy pojedynczych oryginałów ({run.failures.length})</h3>
          <ul aria-label="Błędy oryginałów" className={styles.failures}>
            {run.failures.map((failure, index) => (
              <li key={`${failure.checksumSha256}:${index}`}>
                <code title={failure.checksumSha256}>
                  {shortChecksum(failure.checksumSha256)}
                </code>{' '}
                <strong>{failure.code}</strong>
                {failure.message === '' ? '' : ` — ${failure.message}`}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
