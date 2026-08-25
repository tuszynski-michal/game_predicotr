'use client';

import type {
  RemoteManualSelectionSessionMonitorResponse,
  RemoteManualSelectionSessionResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  loadRemoteManualSelectionAccessCodes,
  rememberRemoteManualSelectionAccessCode,
  removeRemoteManualSelectionAccessCode,
  retainActiveRemoteManualSelectionAccessCodes,
  type RemoteManualSelectionAccessCodeMap,
} from './remote-manual-selection-access-code-cache';
import {
  createRemoteManualSelectionAccess,
  loadRemoteManualSelectionMonitor,
  loadRemoteManualSelectionSessions,
  revokeRemoteManualSelectionAccess,
  type RemoteManualSelectionHostClient,
} from './remote-manual-selection-actions';
import {
  REMOTE_SESSION_FETCH_LIMIT,
  REMOTE_SESSION_LIST_POLL_MS,
  REMOTE_SESSION_MONITOR_POLL_MS,
  filteredRemoteManualSelectionSessions,
  newestRemoteManualSelectionSessions,
  remoteSessionStatusLabel,
  safeRemoteManualSelectionUrl,
  selectVisibleRemoteManualSelectionSessionId,
  type RemoteManualSelectionSessionFilter,
} from './remote-manual-selection-state';

export function RemoteManualSelectionHostPanel({
  apiBaseUrl,
  client,
}: {
  readonly apiBaseUrl: string;
  readonly client?: RemoteManualSelectionHostClient;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [label, setLabel] = useState('');
  const [lifetimeMinutes, setLifetimeMinutes] = useState(480);
  const [sessions, setSessions] = useState<
    readonly RemoteManualSelectionSessionResponse[]
  >([]);
  const [selectedSessionId, setSelectedSessionId] = useState('');
  const [sessionFilter, setSessionFilter] =
    useState<RemoteManualSelectionSessionFilter>('active');
  const [monitor, setMonitor] =
    useState<RemoteManualSelectionSessionMonitorResponse | null>(null);
  const [accessCodes, setAccessCodes] =
    useState<RemoteManualSelectionAccessCodeMap>(() =>
      loadRemoteManualSelectionAccessCodes(),
    );
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [revokingSessionId, setRevokingSessionId] = useState<string | null>(
    null,
  );
  const [revokeConfirmationId, setRevokeConfirmationId] = useState<
    string | null
  >(null);
  const [error, setError] = useState('');
  const [monitorError, setMonitorError] = useState('');
  const [notice, setNotice] = useState('');
  const [copied, setCopied] = useState<string | null>(null);

  const refreshSessions = useCallback(
    async (showError: boolean) => {
      const result = await loadRemoteManualSelectionSessions(api);
      if (!result.ok) {
        if (showError) setError(result.error);
        return;
      }
      const newestSessions = newestRemoteManualSelectionSessions(
        result.data.sessions,
        REMOTE_SESSION_FETCH_LIMIT,
      );
      setSessions(newestSessions);
      setAccessCodes((current) =>
        retainActiveRemoteManualSelectionAccessCodes(
          current,
          newestSessions
            .filter(
              (session) =>
                session.status === 'draft' || session.status === 'active',
            )
            .map((session) => session.sessionId),
        ),
      );
    },
    [api],
  );

  useEffect(() => {
    let active = true;
    void loadRemoteManualSelectionSessions(api).then((result) => {
      if (!active) return;
      if (result.ok) {
        const newestSessions = newestRemoteManualSelectionSessions(
          result.data.sessions,
          REMOTE_SESSION_FETCH_LIMIT,
        );
        setSessions(newestSessions);
        setAccessCodes((current) =>
          retainActiveRemoteManualSelectionAccessCodes(
            current,
            newestSessions
              .filter(
                (session) =>
                  session.status === 'draft' || session.status === 'active',
              )
              .map((session) => session.sessionId),
          ),
        );
      } else {
        setError(result.error);
      }
      setLoading(false);
    });
    const timer = window.setInterval(() => {
      if (active) void refreshSessions(false);
    }, REMOTE_SESSION_LIST_POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [api, refreshSessions]);

  const visibleSessions = useMemo(
    () => filteredRemoteManualSelectionSessions(sessions, sessionFilter),
    [sessionFilter, sessions],
  );
  const visibleSelectedSessionId = selectVisibleRemoteManualSelectionSessionId(
    visibleSessions,
    selectedSessionId,
  );

  const refreshMonitor = useCallback(
    async (sessionId: string, showError: boolean) => {
      if (sessionId === '') {
        setMonitor(null);
        return;
      }
      const result = await loadRemoteManualSelectionMonitor(api, sessionId);
      if (!result.ok) {
        if (showError) setMonitorError(result.error);
        return;
      }
      setMonitorError('');
      setMonitor(result.data);
    },
    [api],
  );

  useEffect(() => {
    let active = true;
    if (visibleSelectedSessionId !== '') {
      void loadRemoteManualSelectionMonitor(api, visibleSelectedSessionId).then(
        (result) => {
          if (!active) return;
          if (result.ok) {
            setMonitorError('');
            setMonitor(result.data);
          } else {
            setMonitorError(result.error);
          }
        },
      );
    }
    const timer = window.setInterval(() => {
      if (active && visibleSelectedSessionId !== '') {
        void refreshMonitor(visibleSelectedSessionId, false);
      }
    }, REMOTE_SESSION_MONITOR_POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [api, refreshMonitor, visibleSelectedSessionId]);

  async function createSession() {
    if (creating || label.trim() === '') return;
    setCreating(true);
    setError('');
    setNotice('');
    setCopied(null);
    try {
      const result = await createRemoteManualSelectionAccess(api, {
        label,
        lifetimeMinutes,
      });
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setAccessCodes((current) =>
        rememberRemoteManualSelectionAccessCode(current, {
          accessCode: result.data.accessCode,
          expiresAt: result.data.session.expiresAt,
          sessionId: result.data.session.sessionId,
        }),
      );
      setSessionFilter('active');
      setSelectedSessionId(result.data.session.sessionId);
      setNotice(
        'Sesja została utworzona. Link i kod pozostają widoczne w danych wybranej sesji.',
      );
      await refreshSessions(false);
      await refreshMonitor(result.data.session.sessionId, false);
    } finally {
      setCreating(false);
    }
  }

  async function revokeSession(sessionId: string) {
    if (revokingSessionId !== null || revokeConfirmationId !== sessionId) {
      setRevokeConfirmationId(sessionId);
      return;
    }
    setRevokingSessionId(sessionId);
    setError('');
    try {
      const result = await revokeRemoteManualSelectionAccess(api, sessionId);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setRevokeConfirmationId(null);
      setAccessCodes((current) =>
        removeRemoteManualSelectionAccessCode(current, sessionId),
      );
      setNotice(
        'Wybrana sesja została zatrzymana. Inne sesje i wspólny tunel nie zostały przerwane.',
      );
      await refreshSessions(false);
      await refreshMonitor(sessionId, false);
    } finally {
      setRevokingSessionId(null);
    }
  }

  async function copyValue(value: string, key: string) {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(key);
    } catch {
      setError('Nie udało się skopiować wartości. Zaznacz ją ręcznie.');
    }
  }

  const currentMonitor =
    monitor?.session.sessionId === visibleSelectedSessionId ? monitor : null;
  const selectedSession =
    currentMonitor?.session ??
    visibleSessions.find(
      (session) => session.sessionId === visibleSelectedSessionId,
    ) ??
    null;
  const selectedReviewUrl =
    selectedSession === null
      ? null
      : safeRemoteManualSelectionUrl(selectedSession);
  const selectedAccessCode =
    selectedSession === null
      ? null
      : (accessCodes[selectedSession.sessionId]?.accessCode ?? null);

  return (
    <section
      className="remoteManualSelectionHostPanel"
      aria-labelledby="remote-manual-selection-host-title"
    >
      <header className="remoteManualSelectionHostHeader">
        <div>
          <p className="eyebrow">Niezależnie od gry · udostępnianie online</p>
          <h2 id="remote-manual-selection-host-title">
            Zdalna ręczna selekcja
          </h2>
          <p>
            Utwórz osobną sesję dla operatora. Link nie zawiera kodu, a folder
            źródłowy, postęp i wybrane obrazy pozostają wyłącznie na urządzeniu
            operatora. Twój komputer przechowuje tylko kod i czas dostępu.
          </p>
        </div>
        <button
          className="secondaryButton"
          disabled={loading}
          onClick={() => void refreshSessions(true)}
          type="button"
        >
          Odśwież sesje
        </button>
      </header>

      <div className="remoteManualSelectionCreate">
        <label>
          Etykieta sesji
          <input
            maxLength={100}
            onChange={(event) => setLabel(event.target.value)}
            placeholder="np. Operator 1 — zakres 1–19809"
            value={label}
          />
        </label>
        <label>
          Czas dostępu
          <select
            onChange={(event) =>
              setLifetimeMinutes(Number.parseInt(event.target.value, 10))
            }
            value={lifetimeMinutes}
          >
            <option value={60}>1 godzina</option>
            <option value={240}>4 godziny</option>
            <option value={480}>8 godzin</option>
            <option value={1440}>24 godziny</option>
          </select>
        </label>
        <button
          className="primaryButton"
          disabled={creating || label.trim() === ''}
          onClick={() => void createSession()}
          type="button"
        >
          {creating ? 'Tworzę sesję…' : 'Utwórz zdalną sesję'}
        </button>
      </div>

      <div className="remoteManualSelectionBody">
        <div className="remoteManualSelectionSessions">
          <div className="remoteManualSelectionSessionListHeader">
            <h3>Najnowsze sesje</h3>
            <label>
              Pokaż
              <select
                aria-label="Filtr najnowszych sesji"
                onChange={(event) =>
                  setSessionFilter(
                    event.target.value as RemoteManualSelectionSessionFilter,
                  )
                }
                value={sessionFilter}
              >
                <option value="active">Aktywne</option>
                <option value="completed">Zakończone</option>
              </select>
            </label>
          </div>
          {loading ? <p role="status">Wczytuję sesje…</p> : null}
          {!loading && visibleSessions.length === 0 ? (
            <p>
              {sessionFilter === 'active'
                ? 'Nie ma aktywnych zdalnych sesji.'
                : 'Nie ma zakończonych zdalnych sesji.'}
            </p>
          ) : null}
          {visibleSessions.map((session) => (
            <button
              className={
                session.sessionId === visibleSelectedSessionId
                  ? 'remoteManualSelectionSession remoteManualSelectionSessionActive'
                  : 'remoteManualSelectionSession'
              }
              key={session.sessionId}
              onClick={() => setSelectedSessionId(session.sessionId)}
              type="button"
            >
              <strong>{session.displayName}</strong>
              <span>{remoteSessionStatusLabel(session.status)}</span>
              <small>{formatDate(session.expiresAt)}</small>
            </button>
          ))}
        </div>

        <div className="remoteManualSelectionMonitor">
          {selectedSession === null ? (
            <p>Wybierz sesję, aby zobaczyć jej stan.</p>
          ) : (
            <>
              <div className="remoteManualSelectionMonitorHeader">
                <div>
                  <h3>{selectedSession.displayName}</h3>
                  <code>ID: {selectedSession.sessionId}</code>
                </div>
                {selectedSession.status === 'active' ? (
                  <button
                    className="dangerButton"
                    disabled={revokingSessionId !== null}
                    onClick={() =>
                      void revokeSession(selectedSession.sessionId)
                    }
                    type="button"
                  >
                    {revokingSessionId === selectedSession.sessionId
                      ? 'Zatrzymuję…'
                      : revokeConfirmationId === selectedSession.sessionId
                        ? 'Potwierdź zatrzymanie tej sesji'
                        : 'Zatrzymaj tę sesję'}
                  </button>
                ) : null}
              </div>
              <div className="remoteManualSelectionMetrics">
                <Metric
                  label="Połączenie"
                  value={selectedSession.ready ? 'online' : 'niedostępne'}
                />
                <Metric
                  label="Operator"
                  value={
                    selectedSession.writerActive ? 'aktywny' : 'nieaktywny'
                  }
                />
                <Metric
                  label="Wolny dysk"
                  value={formatBytes(currentMonitor?.diskFreeBytes ?? null)}
                />
                <Metric
                  label="Ostatni heartbeat"
                  value={
                    selectedSession.lastHeartbeatAt
                      ? formatDate(selectedSession.lastHeartbeatAt)
                      : 'brak'
                  }
                />
                <Metric
                  label="Wygasa"
                  value={formatDate(selectedSession.expiresAt)}
                />
              </div>
              <div className="remoteManualSelectionCredentials">
                <div>
                  <span>Link aplikacji</span>
                  {selectedReviewUrl === null ? (
                    <strong>
                      Brak aktualnego bezpiecznego URL. Odśwież stan po
                      restarcie tunelu.
                    </strong>
                  ) : (
                    <a
                      href={selectedReviewUrl}
                      rel="noreferrer"
                      target="_blank"
                    >
                      {selectedReviewUrl}
                    </a>
                  )}
                  <button
                    className="textButton"
                    disabled={selectedReviewUrl === null}
                    onClick={() =>
                      selectedReviewUrl === null
                        ? undefined
                        : void copyValue(
                            selectedReviewUrl,
                            `${selectedSession.sessionId}:link`,
                          )
                    }
                    type="button"
                  >
                    {copied === `${selectedSession.sessionId}:link`
                      ? 'Skopiowano link'
                      : 'Kopiuj link'}
                  </button>
                </div>
                <div>
                  <span>Kod wejścia</span>
                  <code>
                    {selectedAccessCode ??
                      'Kod nie jest dostępny na tym komputerze'}
                  </code>
                  <button
                    className="textButton"
                    disabled={selectedAccessCode === null}
                    onClick={() =>
                      selectedAccessCode === null
                        ? undefined
                        : void copyValue(
                            selectedAccessCode,
                            `${selectedSession.sessionId}:code`,
                          )
                    }
                    type="button"
                  >
                    {copied === `${selectedSession.sessionId}:code`
                      ? 'Skopiowano kod'
                      : 'Kopiuj kod'}
                  </button>
                </div>
                <small>
                  Kod jest zapisany wyłącznie lokalnie na tym komputerze do
                  wygaśnięcia albo zatrzymania sesji.
                </small>
              </div>
              <div className="remoteManualSelectionLink">
                <button
                  className="textButton"
                  onClick={() =>
                    void refreshMonitor(selectedSession.sessionId, true)
                  }
                  type="button"
                >
                  Odśwież stan
                </button>
              </div>
              {currentMonitor?.diskErrorCode ? (
                <p className="formError">
                  Dysk: {currentMonitor.diskErrorCode}
                </p>
              ) : null}
              {monitorError ? (
                <p className="formError" role="alert">
                  {monitorError}
                </p>
              ) : null}
            </>
          )}
        </div>
      </div>

      {notice ? (
        <p className="formSuccess" role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p className="formError" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

function Metric({
  label,
  value,
}: {
  readonly label: string;
  readonly value: string;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatBytes(value: number | null): string {
  if (value === null) return 'brak danych';
  return `${(value / 1024 ** 3).toLocaleString('pl-PL', { maximumFractionDigits: 1 })} GB`;
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('pl-PL', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value));
}
