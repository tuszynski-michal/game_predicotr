'use client';

import type {
  RemoteManualSelectionSessionCreatedResponse,
  RemoteManualSelectionSessionMonitorResponse,
  RemoteManualSelectionSessionResponse,
  RemoteSelectionRecoveryStatusResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  createRemoteManualSelectionAccess,
  loadRemoteManualSelectionMonitor,
  loadRemoteManualSelectionRecoveryStatus,
  loadRemoteManualSelectionSessions,
  reopenRemoteManualSelectionBatch,
  revokeRemoteManualSelectionAccess,
  type RemoteManualSelectionHostClient,
} from './remote-manual-selection-actions';
import {
  REMOTE_SESSION_LIST_POLL_MS,
  REMOTE_SESSION_MONITOR_POLL_MS,
  remoteSessionStatusLabel,
  safeRemoteManualSelectionUrl,
  selectRemoteManualSelectionSessionId,
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
  const [monitor, setMonitor] =
    useState<RemoteManualSelectionSessionMonitorResponse | null>(null);
  const [oneTimeAccess, setOneTimeAccess] =
    useState<RemoteManualSelectionSessionCreatedResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [revokingSessionId, setRevokingSessionId] = useState<string | null>(
    null,
  );
  const [revokeConfirmationId, setRevokeConfirmationId] = useState<
    string | null
  >(null);
  const [reopenConfirmationId, setReopenConfirmationId] = useState<
    string | null
  >(null);
  const [reopeningBatchId, setReopeningBatchId] = useState<string | null>(null);
  const [recoveryBatchId, setRecoveryBatchId] = useState<string | null>(null);
  const [recoveryStatus, setRecoveryStatus] =
    useState<RemoteSelectionRecoveryStatusResponse | null>(null);
  const [error, setError] = useState('');
  const [monitorError, setMonitorError] = useState('');
  const [notice, setNotice] = useState('');
  const [copied, setCopied] = useState<'code' | 'link' | null>(null);

  const refreshSessions = useCallback(
    async (showError: boolean) => {
      const result = await loadRemoteManualSelectionSessions(api);
      if (!result.ok) {
        if (showError) setError(result.error);
        return;
      }
      setSessions(result.data.sessions);
      setSelectedSessionId((current) =>
        selectRemoteManualSelectionSessionId(result.data.sessions, current),
      );
    },
    [api],
  );

  useEffect(() => {
    let active = true;
    void loadRemoteManualSelectionSessions(api).then((result) => {
      if (!active) return;
      if (result.ok) {
        setSessions(result.data.sessions);
        setSelectedSessionId(
          selectRemoteManualSelectionSessionId(result.data.sessions, ''),
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
    if (selectedSessionId !== '') {
      void loadRemoteManualSelectionMonitor(api, selectedSessionId).then(
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
      if (active && selectedSessionId !== '') {
        void refreshMonitor(selectedSessionId, false);
      }
    }, REMOTE_SESSION_MONITOR_POLL_MS);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [api, refreshMonitor, selectedSessionId]);

  async function createSession() {
    if (creating || label.trim() === '') return;
    setCreating(true);
    setError('');
    setNotice('');
    setOneTimeAccess(null);
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
      setOneTimeAccess(result.data);
      setSelectedSessionId(result.data.session.sessionId);
      setNotice(
        'Sesja została utworzona. Kod skopiuj przed zamknięciem karty.',
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
      setOneTimeAccess((current) =>
        current?.session.sessionId === sessionId ? null : current,
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

  async function copyValue(value: string, kind: 'code' | 'link') {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(kind);
    } catch {
      setError('Nie udało się skopiować wartości. Zaznacz ją ręcznie.');
    }
  }

  async function reopenBatch(
    sessionId: string,
    batch: RemoteManualSelectionSessionMonitorResponse['batches'][number],
  ) {
    if (
      batch.finalManifestChecksumSha256 === null ||
      batch.finalManifestChecksumSha256 === undefined
    ) {
      setError('Zakończona partia nie ma kontrolnej sumy manifestu.');
      return;
    }
    if (reopenConfirmationId !== batch.batchId) {
      setReopenConfirmationId(batch.batchId);
      return;
    }
    setReopeningBatchId(batch.batchId);
    setError('');
    try {
      const result = await reopenRemoteManualSelectionBatch(api, {
        batchId: batch.batchId,
        expectedFinalManifestChecksumSha256: batch.finalManifestChecksumSha256,
        expectedServerRevision: batch.serverRevision,
        sessionId,
      });
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setReopenConfirmationId(null);
      setNotice(
        `Partia ${batch.name} została ponownie otwarta. Opublikowane manifesty pozostają audytowalne do następnej finalizacji.`,
      );
      await refreshMonitor(sessionId, false);
    } finally {
      setReopeningBatchId(null);
    }
  }

  async function loadRecovery(sessionId: string, batchId: string) {
    if (recoveryBatchId !== null) return;
    setRecoveryBatchId(batchId);
    setRecoveryStatus(null);
    setMonitorError('');
    const result = await loadRemoteManualSelectionRecoveryStatus(
      api,
      sessionId,
      batchId,
    );
    if (result.ok) setRecoveryStatus(result.data);
    else setMonitorError(result.error);
    setRecoveryBatchId(null);
  }

  const currentMonitor =
    monitor?.session.sessionId === selectedSessionId ? monitor : null;
  const selectedSession =
    currentMonitor?.session ??
    sessions.find((session) => session.sessionId === selectedSessionId) ??
    null;
  const selectedReviewUrl =
    selectedSession === null
      ? null
      : safeRemoteManualSelectionUrl(selectedSession);
  const oneTimeReviewUrl = safeRemoteManualSelectionUrl(
    oneTimeAccess?.session ?? emptySession,
  );

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

      {oneTimeAccess !== null ? (
        <div className="remoteManualSelectionSecret" role="status">
          <div>
            <strong>Kod jednorazowy — nie pojawi się po odświeżeniu</strong>
            <code>{oneTimeAccess.accessCode}</code>
          </div>
          <button
            className="secondaryButton"
            onClick={() => void copyValue(oneTimeAccess.accessCode, 'code')}
            type="button"
          >
            {copied === 'code' ? 'Skopiowano kod' : 'Kopiuj kod'}
          </button>
          {oneTimeReviewUrl !== null ? (
            <button
              className="secondaryButton"
              onClick={() => void copyValue(oneTimeReviewUrl, 'link')}
              type="button"
            >
              {copied === 'link' ? 'Skopiowano link' : 'Kopiuj link'}
            </button>
          ) : (
            <span>Ingress jeszcze nie zwrócił bezpiecznego adresu.</span>
          )}
          <button
            className="textButton"
            onClick={() => setOneTimeAccess(null)}
            type="button"
          >
            Ukryj kod
          </button>
        </div>
      ) : null}

      <div className="remoteManualSelectionBody">
        <div className="remoteManualSelectionSessions">
          <h3>Sesje</h3>
          {loading ? <p role="status">Wczytuję sesje…</p> : null}
          {!loading && sessions.length === 0 ? (
            <p>Nie ma jeszcze żadnej zdalnej sesji.</p>
          ) : null}
          {sessions.map((session) => (
            <button
              className={
                session.sessionId === selectedSessionId
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
              <div className="remoteManualSelectionLink">
                {selectedReviewUrl === null ? (
                  <span>
                    Brak aktualnego bezpiecznego URL. Po restarcie tunelu
                    kliknij „Odśwież stan”.
                  </span>
                ) : (
                  <>
                    <a
                      href={selectedReviewUrl}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Otwórz bieżący link
                    </a>
                    <button
                      className="textButton"
                      onClick={() => void copyValue(selectedReviewUrl, 'link')}
                      type="button"
                    >
                      Kopiuj link
                    </button>
                  </>
                )}
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
              <div className="remoteManualSelectionBatches">
                <h4>Partie (maksymalnie 100)</h4>
                {currentMonitor === null ? (
                  <p role="status">Wczytuję liczniki…</p>
                ) : currentMonitor.batches.length === 0 ? (
                  <p>Operator nie utworzył jeszcze partii.</p>
                ) : (
                  <div className="tableScroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Partia</th>
                          <th>Status</th>
                          <th>Wybrane</th>
                          <th>Zapisane</th>
                          <th>Oczekujące akcje</th>
                          <th>Błędy</th>
                          <th>Akcje</th>
                        </tr>
                      </thead>
                      <tbody>
                        {currentMonitor.batches.map((batch) => (
                          <tr key={batch.batchId}>
                            <td>{batch.name}</td>
                            <td>{batch.status}</td>
                            <td>
                              {batch.selectedFileCount} / {batch.totalFileCount}
                            </td>
                            <td>{batch.syncedFileCount}</td>
                            <td>{batch.pendingHostActionCount}</td>
                            <td>
                              {batch.failedFileCount > 0
                                ? `${batch.failedFileCount}: ${batch.lastErrorCodes.join(', ') || 'REMOTE_SELECTION_FILE_FAILED'}`
                                : '0'}
                            </td>
                            <td>
                              <button
                                className="textButton"
                                disabled={recoveryBatchId !== null}
                                onClick={() =>
                                  void loadRecovery(
                                    selectedSession.sessionId,
                                    batch.batchId,
                                  )
                                }
                                type="button"
                              >
                                {recoveryBatchId === batch.batchId
                                  ? 'Sprawdzam…'
                                  : 'Diagnostyka'}
                              </button>
                              {batch.status === 'completed' ? (
                                <button
                                  className="textButton"
                                  disabled={reopeningBatchId !== null}
                                  onClick={() =>
                                    void reopenBatch(
                                      selectedSession.sessionId,
                                      batch,
                                    )
                                  }
                                  type="button"
                                >
                                  {reopeningBatchId === batch.batchId
                                    ? 'Otwieram…'
                                    : reopenConfirmationId === batch.batchId
                                      ? 'Potwierdź ponowne otwarcie'
                                      : 'Otwórz ponownie'}
                                </button>
                              ) : null}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                {recoveryStatus !== null ? (
                  <div className="remoteManualSelectionRecovery" role="status">
                    <h5>Diagnostyka partii</h5>
                    <p>
                      Upload: {recoveryStatus.queue.uploadingTransferCount} ·
                      materializacja:{' '}
                      {recoveryStatus.queue.materializingActionCount} ·
                      konflikty: {recoveryStatus.queue.conflictFileCount}
                    </p>
                    <p>
                      Preview GC:{' '}
                      {recoveryStatus.gcPreview.scannedArtifactCount} artefaktów
                      / {formatBytes(recoveryStatus.gcPreview.scannedBytes)}.
                      Usuwanie jest wyłączone.
                    </p>
                    {recoveryStatus.queue.recoveryFindings.length > 0 ? (
                      <ul>
                        {recoveryStatus.queue.recoveryFindings.map(
                          (finding) => (
                            <li key={finding.code}>
                              {finding.code}: {finding.count}
                            </li>
                          ),
                        )}
                      </ul>
                    ) : (
                      <p>Brak aktywnych findings recovery.</p>
                    )}
                  </div>
                ) : null}
                {currentMonitor?.hasMoreBatches ? (
                  <p>Widok ograniczono do 100 najnowszych partii.</p>
                ) : null}
              </div>
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

const emptySession: RemoteManualSelectionSessionResponse = {
  createdAt: '',
  displayName: '',
  expiresAt: '',
  lockedAt: null,
  lastHeartbeatAt: null,
  ready: false,
  revision: 0,
  reviewUrl: null,
  revokedAt: null,
  sessionId: '',
  status: 'draft',
  updatedAt: '',
  writerActive: false,
  writerLeaseExpiresAt: null,
};
