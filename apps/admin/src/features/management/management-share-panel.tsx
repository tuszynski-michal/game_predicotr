'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  createManagementLinkClient,
  type ManagementLinkClient,
  type ManagementSessionResponse,
  type ManagementSessionCreate,
} from '@game-predictor/admin-api-client';
import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import { BOARD_SEARCH_SHARE_LIFETIMES } from '../board-search/board-search-share-state';
import { managementError } from './management-client';

const CODE_KEY = 'game-predictor:management:local-link-codes:v1';
type Codes = Record<string, { code: string; expiresAt: string }>;
function readCodes(): Codes {
  try {
    const value: unknown = JSON.parse(
      window.localStorage.getItem(CODE_KEY) ?? '{}',
    );
    if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
    const result: Codes = {};
    for (const [id, item] of Object.entries(value)) {
      if (
        item &&
        typeof item === 'object' &&
        'code' in item &&
        typeof item.code === 'string' &&
        /^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(item.code) &&
        'expiresAt' in item &&
        typeof item.expiresAt === 'string' &&
        Date.parse(item.expiresAt) > Date.now()
      )
        result[id] = { code: item.code, expiresAt: item.expiresAt };
    }
    return result;
  } catch {
    return {};
  }
}

export function ManagementSharePanel({
  apiBaseUrl,
  client,
}: {
  apiBaseUrl: string;
  client?: ManagementLinkClient;
}) {
  const api = useMemo(
    () =>
      client ??
      createManagementLinkClient({
        baseUrl: resolveAdminApiBaseUrl(apiBaseUrl),
      }),
    [apiBaseUrl, client],
  );
  const [open, setOpen] = useState(false);
  const [sessions, setSessions] = useState<
    readonly ManagementSessionResponse[]
  >([]);
  const [codes, setCodes] = useState<Codes>({});
  const [label, setLabel] = useState('');
  const [lifetime, setLifetime] =
    useState<ManagementSessionCreate['lifetimeMinutes']>(480);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [notice, setNotice] = useState('');
  const lock = useRef(false);
  const generation = useRef(0);
  const store = (next: Codes) => {
    setCodes(next);
    try {
      window.localStorage.setItem(CODE_KEY, JSON.stringify(next));
    } catch {
      /* The code remains visible in this tab. */
    }
  };
  const load = useCallback(async () => {
    if (lock.current) return;
    const current = ++generation.current;
    setLoading(true);
    try {
      const response = await api.listManagementSessions();
      if (current !== generation.current) return;
      if (!response.data) throw response.error;
      setSessions(response.data.sessions);
      const retained = readCodes();
      for (const session of response.data.sessions)
        if (session.status !== 'active') delete retained[session.sessionId];
      setCodes(retained);
      try {
        window.localStorage.setItem(CODE_KEY, JSON.stringify(retained));
      } catch {
        /* Optional local cache. */
      }
    } catch (error) {
      if (current === generation.current)
        setNotice(managementError(error, 'Nie udało się wczytać linków.'));
    } finally {
      if (current === generation.current) setLoading(false);
    }
  }, [api]);
  useEffect(() => {
    let disposed = false;
    const requestGeneration = generation;
    if (open)
      queueMicrotask(() => {
        if (!disposed) void load();
      });
    return () => {
      disposed = true;
      requestGeneration.current++;
    };
  }, [open, load]);
  const create = async () => {
    if (lock.current || !label.trim()) return;
    lock.current = true;
    generation.current++;
    setLoading(false);
    setBusy(true);
    setNotice('');
    try {
      const response = await api.createManagementSession({
        label: label.trim(),
        lifetimeMinutes: lifetime,
      });
      if (!response.data) throw response.error;
      const { session, accessCode } = response.data;
      store({
        ...readCodes(),
        [session.sessionId]: { code: accessCode, expiresAt: session.expiresAt },
      });
      setSessions((previous) => [session, ...previous]);
      setNotice(
        'Link i kod są osobne. Odbiorca zarządza całym panelem i poprawia symbole przypisanych gier. Komputer musi działać.',
      );
    } catch (error) {
      setNotice(managementError(error, 'Nie udało się utworzyć linku.'));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const revoke = async (session: ManagementSessionResponse) => {
    if (
      lock.current ||
      !window.confirm(
        `Zatrzymać dostęp „${session.label}”? Historia zostanie zachowana.`,
      )
    )
      return;
    lock.current = true;
    generation.current++;
    setLoading(false);
    setBusy(true);
    setNotice('');
    try {
      const response = await api.revokeManagementSession(session.sessionId);
      if (!response.data) throw response.error;
      const next = readCodes();
      delete next[session.sessionId];
      store(next);
      setSessions((previous) =>
        previous.map((item) =>
          item.sessionId === session.sessionId ? response.data! : item,
        ),
      );
    } catch (error) {
      setNotice(managementError(error, 'Nie udało się zatrzymać linku.'));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setNotice('Skopiowano.');
    } catch {
      setNotice('Zaznacz i skopiuj widoczny tekst.');
    }
  };
  return (
    <div>
      <button
        type="button"
        disabled={busy}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        Udostępnij panel online
      </button>
      {open && (
        <section className="catalog-panel" aria-label="Linki panelu online">
          <h3>Cały Panel Administracyjny online</h3>
          <p>
            Odbiorca zarządza punktami, maszynami, zapisami i symbolami
            przypisanych gier. Kod przekazuj osobno. Komputer i API muszą
            działać.
          </p>
          <label>
            Nazwa odbiorcy
            <input
              value={label}
              maxLength={100}
              disabled={busy}
              onChange={(event) => setLabel(event.target.value)}
            />
          </label>
          <label>
            Czas dostępu
            <select
              value={lifetime}
              disabled={busy}
              onChange={(event) =>
                setLifetime(
                  Number(
                    event.target.value,
                  ) as ManagementSessionCreate['lifetimeMinutes'],
                )
              }
            >
              {BOARD_SEARCH_SHARE_LIFETIMES.map((item) => (
                <option key={item.minutes} value={item.minutes}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy || !label.trim()}
            onClick={() => void create()}
          >
            Utwórz link
          </button>
          <button
            type="button"
            disabled={busy || loading}
            onClick={() => void load()}
          >
            Odśwież linki
          </button>
          {notice && <p role="status">{notice}</p>}
          {loading && <p>Wczytywanie linków…</p>}
          {!loading && sessions.length === 0 && <p>Brak linków panelu.</p>}
          {sessions.map((session) => (
            <article className="management-tile" key={session.sessionId}>
              <strong>{session.label}</strong>
              <p>
                {
                  {
                    active: 'Aktywny',
                    locked: 'Zablokowany po błędnych kodach',
                    expired: 'Wygasł',
                    revoked: 'Zatrzymany',
                  }[session.status]
                }{' '}
                · do {new Date(session.expiresAt).toLocaleString('pl-PL')}
              </p>
              {session.shareUrl && (
                <>
                  <p>
                    <a href={session.shareUrl} target="_blank" rel="noreferrer">
                      {session.shareUrl}
                    </a>
                  </p>
                  <button
                    type="button"
                    onClick={() => void copy(session.shareUrl!)}
                  >
                    Kopiuj link
                  </button>
                </>
              )}
              {session.status === 'active' && codes[session.sessionId] && (
                <>
                  <p>
                    Kod: <code>{codes[session.sessionId].code}</code>
                  </p>
                  <button
                    type="button"
                    onClick={() => void copy(codes[session.sessionId].code)}
                  >
                    Kopiuj kod
                  </button>
                </>
              )}
              {session.status === 'active' && !codes[session.sessionId] && (
                <p>Kod jest dostępny w przeglądarce, która utworzyła link.</p>
              )}
              {session.status === 'active' && (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void revoke(session)}
                >
                  Zatrzymaj dostęp
                </button>
              )}
            </article>
          ))}
        </section>
      )}
    </div>
  );
}
