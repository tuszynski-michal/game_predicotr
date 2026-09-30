'use client';

import type {
  AdminApiClient,
  BoardSearchShareSessionResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useId, useRef, useState } from 'react';

import {
  type BoardSearchShareCodeMap,
  loadBoardSearchShareCodes,
  rememberBoardSearchShareCode,
  removeBoardSearchShareCode,
  removeEndedBoardSearchShareCodes,
} from './board-search-share-code-cache';
import { BoardSearchShareQueryLog } from './board-search-share-query-log';
import {
  BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES,
  BOARD_SEARCH_SHARE_LIFETIMES,
  boardSearchShareErrorMessage,
  boardSearchShareStatusLabel,
  formatBoardSearchShareDate,
  groupBoardSearchShareSessions,
} from './board-search-share-state';

export type BoardSearchShareClient = Pick<
  AdminApiClient,
  | 'createBoardSearchShareSession'
  | 'listBoardSearchShareQueries'
  | 'listBoardSearchShareSessions'
  | 'listSymbols'
  | 'revokeBoardSearchShareSession'
  | 'symbolImageAssetUrl'
>;

type ListState =
  | { readonly kind: 'loading' }
  | { readonly kind: 'error'; readonly message: string }
  | {
      readonly kind: 'ready';
      readonly sessions: readonly BoardSearchShareSessionResponse[];
    };

/**
 * "Udostępnij online" (D-471): creates a read-only share link with a
 * separate access code and manages the game's links. Admin-only; the
 * recipient never sees this panel.
 */
export function BoardSearchSharePanel({
  client,
  gameId,
  onReplay,
}: {
  readonly client: BoardSearchShareClient;
  readonly gameId: string;
  /** Opens a query log entry in this board search (D-472). */
  readonly onReplay: (eventId: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [label, setLabel] = useState('');
  const [lifetime, setLifetime] = useState<number>(
    BOARD_SEARCH_SHARE_DEFAULT_LIFETIME_MINUTES,
  );
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<{
    readonly kind: 'ok' | 'error';
    readonly text: string;
  } | null>(null);
  const [list, setList] = useState<ListState>({ kind: 'loading' });
  const [codes, setCodes] = useState<BoardSearchShareCodeMap>({});
  const [confirmRevoke, setConfirmRevoke] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [freshSessionId, setFreshSessionId] = useState<string | null>(null);
  const [logSessionId, setLogSessionId] = useState<string | null>(null);
  const requestId = useRef(0);
  const panelId = useId();

  const load = useCallback(async () => {
    const current = ++requestId.current;
    try {
      const result = await client.listBoardSearchShareSessions({ gameId });
      if (current !== requestId.current) return;
      if (result.error !== undefined || result.data === undefined) {
        setList({
          kind: 'error',
          message: boardSearchShareErrorMessage(
            result.error,
            'Nie udało się pobrać linków udostępniania.',
          ),
        });
        return;
      }
      const sessions = result.data.sessions;
      setList({ kind: 'ready', sessions });
      // The list covers this game only: forget the codes of its ended links
      // and keep other games' codes (expired codes drop out on load).
      setCodes(
        removeEndedBoardSearchShareCodes(
          loadBoardSearchShareCodes(),
          sessions
            .filter((session) => session.status !== 'active')
            .map((session) => session.sessionId),
        ),
      );
    } catch {
      if (current === requestId.current) {
        setList({
          kind: 'error',
          message: 'Połączenie z lokalnym Admin API zostało przerwane.',
        });
      }
    }
  }, [client, gameId]);

  useEffect(() => {
    if (!open) return;
    const timeout = window.setTimeout(() => {
      setCodes(loadBoardSearchShareCodes());
      void load();
    }, 0);
    return () => window.clearTimeout(timeout);
  }, [load, open]);

  async function create() {
    if (creating) return;
    setCreating(true);
    setNotice(null);
    try {
      const result = await client.createBoardSearchShareSession({
        gameId,
        label: label.trim() === '' ? null : label.trim(),
        lifetimeMinutes: lifetime,
      });
      if (result.error !== undefined || result.data === undefined) {
        setNotice({
          kind: 'error',
          text: boardSearchShareErrorMessage(
            result.error,
            'Nie udało się utworzyć linku.',
          ),
        });
        return;
      }
      const created = result.data;
      // Stored right away, outside React state: the panel may already be
      // unmounted (section collapsed, game switched) after a slow tunnel
      // start, and the API never returns the code again.
      setCodes(
        rememberBoardSearchShareCode(loadBoardSearchShareCodes(), {
          accessCode: created.accessCode,
          expiresAt: created.session.expiresAt,
          sessionId: created.session.sessionId,
        }),
      );
      setFreshSessionId(created.session.sessionId);
      setLabel('');
      setNotice({
        kind: 'ok',
        text: 'Link utworzony. Wyślij link i kod osobnymi wiadomościami.',
      });
      await load();
    } catch {
      setNotice({
        kind: 'error',
        text: 'Połączenie z lokalnym Admin API zostało przerwane.',
      });
    } finally {
      setCreating(false);
    }
  }

  async function revoke(sessionId: string) {
    if (revoking !== null) return;
    setRevoking(sessionId);
    setNotice(null);
    try {
      const result = await client.revokeBoardSearchShareSession(sessionId);
      if (result.error !== undefined) {
        setNotice({
          kind: 'error',
          text: boardSearchShareErrorMessage(
            result.error,
            'Nie udało się zatrzymać linku.',
          ),
        });
        return;
      }
      setCodes(
        removeBoardSearchShareCode(loadBoardSearchShareCodes(), sessionId),
      );
      setConfirmRevoke(null);
      setNotice({
        kind: 'ok',
        text: 'Link zatrzymany. Odbiorca stracił dostęp.',
      });
      await load();
    } catch {
      setNotice({
        kind: 'error',
        text: 'Połączenie z lokalnym Admin API zostało przerwane.',
      });
    } finally {
      setRevoking(null);
    }
  }

  async function copy(text: string, what: string) {
    try {
      await navigator.clipboard.writeText(text);
      setNotice({ kind: 'ok', text: `Skopiowano ${what}.` });
    } catch {
      setNotice({
        kind: 'error',
        text: `Nie udało się skopiować ${what} — zaznacz i skopiuj ręcznie.`,
      });
    }
  }

  const groups =
    list.kind === 'ready' ? groupBoardSearchShareSessions(list.sessions) : null;

  return (
    <div className="boardSearchShare">
      <button
        aria-controls={panelId}
        aria-expanded={open}
        className="secondaryButton"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        {open ? 'Zamknij udostępnianie' : 'Udostępnij online'}
      </button>
      {open ? (
        <section
          aria-label="Udostępnianie wyszukiwarki online"
          className="boardSearchSharePanel"
          id={panelId}
        >
          <p className="boardSearchShareHint">
            Link otwiera tylko do odczytu kopię tej sekcji dla tej gry (bez
            poprawiania pól). Kod dostępu wysyłaj osobno. Zapytania odbiorcy są
            zapisywane.
          </p>
          <div className="boardSearchShareCreate">
            <label>
              <span>Etykieta (opcjonalnie)</span>
              <input
                maxLength={100}
                onChange={(event) => setLabel(event.currentTarget.value)}
                placeholder="np. Dla Ani"
                value={label}
              />
            </label>
            <label>
              <span>Czas dostępu</span>
              <select
                onChange={(event) =>
                  setLifetime(Number(event.currentTarget.value))
                }
                value={lifetime}
              >
                {BOARD_SEARCH_SHARE_LIFETIMES.map((option) => (
                  <option key={option.minutes} value={option.minutes}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              className="primaryButton"
              disabled={creating}
              onClick={() => void create()}
              type="button"
            >
              {creating ? 'Tworzenie…' : 'Utwórz link'}
            </button>
          </div>
          {notice !== null ? (
            <p
              className={
                notice.kind === 'error'
                  ? 'feedbackBanner feedbackBannerError'
                  : 'feedbackBanner'
              }
              role={notice.kind === 'error' ? 'alert' : 'status'}
            >
              {notice.text}
            </p>
          ) : null}
          {list.kind === 'loading' ? (
            <p role="status">Wczytywanie linków…</p>
          ) : null}
          {list.kind === 'error' ? (
            <p className="feedbackBanner feedbackBannerError" role="alert">
              {list.message}
            </p>
          ) : null}
          {groups !== null ? (
            <>
              <h3>Aktywne linki</h3>
              {groups.active.length === 0 ? (
                <p className="boardSearchShareEmpty">Brak aktywnych linków.</p>
              ) : (
                <ul className="boardSearchShareList">
                  {groups.active.map((session) => {
                    const code = codes[session.sessionId]?.accessCode ?? null;
                    const confirming = confirmRevoke === session.sessionId;
                    return (
                      <li
                        className={
                          session.sessionId === freshSessionId
                            ? 'boardSearchShareItem boardSearchShareItemFresh'
                            : 'boardSearchShareItem'
                        }
                        key={session.sessionId}
                      >
                        <div className="boardSearchShareItemHeader">
                          <strong>{session.label ?? 'Bez etykiety'}</strong>
                          <span>
                            wygasa{' '}
                            {formatBoardSearchShareDate(session.expiresAt)}
                            {session.lastUnlockedAt !== null
                              ? ` · ostatnie otwarcie ${formatBoardSearchShareDate(session.lastUnlockedAt)}`
                              : ' · jeszcze nieotwarty'}
                          </span>
                        </div>
                        {session.shareUrl !== null ? (
                          <div className="boardSearchShareSecret">
                            <span>Link</span>
                            <code>{session.shareUrl}</code>
                            <button
                              className="textButton"
                              onClick={() =>
                                void copy(session.shareUrl ?? '', 'link')
                              }
                              type="button"
                            >
                              Kopiuj link
                            </button>
                          </div>
                        ) : (
                          <p className="boardSearchShareHint">
                            Publiczny adres Reviewera nie działa — link pojawi
                            się po jego uruchomieniu.
                          </p>
                        )}
                        <div className="boardSearchShareSecret">
                          <span>Kod</span>
                          {code !== null ? (
                            <>
                              <code>{code}</code>
                              <button
                                className="textButton"
                                onClick={() => void copy(code, 'kod')}
                                type="button"
                              >
                                Kopiuj kod
                              </button>
                            </>
                          ) : (
                            <em>
                              kod znany tylko w przeglądarce, która utworzyła
                              link
                            </em>
                          )}
                        </div>
                        <QueryLogToggle
                          client={client}
                          gameId={gameId}
                          logSessionId={logSessionId}
                          onReplay={onReplay}
                          onToggle={setLogSessionId}
                          sessionId={session.sessionId}
                        />
                        <div className="boardSearchShareActions">
                          {confirming ? (
                            <>
                              <button
                                className="primaryButton"
                                disabled={revoking !== null}
                                onClick={() => void revoke(session.sessionId)}
                                type="button"
                              >
                                {revoking === session.sessionId
                                  ? 'Zatrzymywanie…'
                                  : 'Potwierdź zatrzymanie'}
                              </button>
                              <button
                                className="textButton"
                                disabled={revoking !== null}
                                onClick={() => setConfirmRevoke(null)}
                                type="button"
                              >
                                Anuluj
                              </button>
                            </>
                          ) : (
                            <button
                              className="secondaryButton"
                              disabled={revoking !== null}
                              onClick={() =>
                                setConfirmRevoke(session.sessionId)
                              }
                              type="button"
                            >
                              Zatrzymaj
                            </button>
                          )}
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
              {groups.ended.length > 0 ? (
                <details className="boardSearchShareEnded">
                  <summary>Zakończone linki ({groups.ended.length})</summary>
                  <ul className="boardSearchShareList">
                    {groups.ended.map((session) => (
                      <li
                        className="boardSearchShareItem"
                        key={session.sessionId}
                      >
                        <div className="boardSearchShareItemHeader">
                          <strong>{session.label ?? 'Bez etykiety'}</strong>
                          <span>
                            {boardSearchShareStatusLabel(session.status)} ·
                            utworzony{' '}
                            {formatBoardSearchShareDate(session.createdAt)}
                          </span>
                        </div>
                        <QueryLogToggle
                          client={client}
                          gameId={gameId}
                          logSessionId={logSessionId}
                          onReplay={onReplay}
                          onToggle={setLogSessionId}
                          sessionId={session.sessionId}
                        />
                      </li>
                    ))}
                  </ul>
                </details>
              ) : null}
            </>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}

function QueryLogToggle({
  client,
  gameId,
  logSessionId,
  onReplay,
  onToggle,
  sessionId,
}: {
  readonly client: BoardSearchShareClient;
  readonly gameId: string;
  readonly logSessionId: string | null;
  readonly onReplay: (eventId: string) => void;
  readonly onToggle: (sessionId: string | null) => void;
  readonly sessionId: string;
}) {
  const open = logSessionId === sessionId;
  return (
    <div className="boardSearchShareLogToggle">
      <button
        aria-expanded={open}
        className="textButton"
        onClick={() => onToggle(open ? null : sessionId)}
        type="button"
      >
        {open ? 'Ukryj dziennik zapytań' : 'Dziennik zapytań'}
      </button>
      {open ? (
        <BoardSearchShareQueryLog
          client={client}
          gameId={gameId}
          onReplay={onReplay}
          sessionId={sessionId}
        />
      ) : null}
    </div>
  );
}
