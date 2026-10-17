'use client';

import type {
  AdminApiClient,
  BoardSearchPanelResponse,
  GameResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  BoardSearchShareQueryLog,
  type BoardSearchShareQueryLogClient,
} from '../board-search/board-search-share-query-log';
import {
  BOARD_SEARCH_SHARE_LIFETIMES,
  formatBoardSearchShareDate,
} from '../board-search/board-search-share-state';
import {
  loadPanelKeys,
  panelShareUrl,
  storePanelKeys,
  type PanelKeys,
} from './board-search-panel-keys';
import { panelErrorMessage } from './board-search-panel-state';

export type BoardSearchSharingClient = Pick<
  AdminApiClient,
  | 'listGames'
  | 'createBoardSearchPanel'
  | 'listBoardSearchPanels'
  | 'revokeBoardSearchPanel'
> &
  BoardSearchShareQueryLogClient;

export function BoardSearchSharingWorkspace({
  client,
  onReplay,
}: {
  readonly client: BoardSearchSharingClient;
  readonly onReplay: (eventId: string) => void;
}) {
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [panels, setPanels] = useState<readonly BoardSearchPanelResponse[]>([]);
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [keys, setKeys] = useState<PanelKeys>({});
  const [label, setLabel] = useState('');
  const [lifetime, setLifetime] = useState(480);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [log, setLog] = useState<{
    readonly panelId: string;
    readonly sessionId: string;
  } | null>(null);
  const revision = useRef(0);
  const submitting = useRef(false);

  const load = useCallback(async () => {
    const current = ++revision.current;
    setLoading(true);
    setError('');
    try {
      const [g, p] = await Promise.all([
        client.listGames(),
        client.listBoardSearchPanels(),
      ]);
      if (current !== revision.current) return;
      if (!g.data || !p.data || g.error || p.error) {
        setError(
          panelErrorMessage(
            g.error ?? p.error,
            'Nie udało się pobrać gier i linków.',
          ),
        );
        return;
      }
      setGames(g.data.filter((game) => game.status !== 'archived'));
      const available = new Set(
        g.data
          .filter((game) => game.status !== 'archived')
          .map((game) => game.id),
      );
      setSelected((previous) => previous.filter((id) => available.has(id)));
      setPanels(p.data.panels);
      setKeys((currentKeys) => {
        const merged = { ...loadPanelKeys(), ...currentKeys };
        const ended = new Set(
          p.data.panels
            .filter((panel) => panel.status !== 'active')
            .map((panel) => panel.panelId),
        );
        const active = Object.fromEntries(
          Object.entries(merged).filter(
            ([id, key]) =>
              !ended.has(id) && Date.parse(key.expiresAt) > Date.now(),
          ),
        );
        storePanelKeys(active);
        return active;
      });
    } catch {
      if (current === revision.current)
        setError('Połączenie z lokalnym API zostało przerwane.');
    } finally {
      if (current === revision.current) setLoading(false);
    }
  }, [client]);
  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => {
      window.clearTimeout(timer);
      revision.current += 1;
    };
  }, [load]);

  async function create() {
    if (submitting.current || selected.length === 0) return;
    submitting.current = true;
    setBusy(true);
    setNotice('');
    setError('');
    try {
      const result = await client.createBoardSearchPanel({
        gameIds: [...selected],
        label: label.trim() || null,
        lifetimeMinutes: lifetime,
      });
      if (!result.data || result.error) {
        setError(
          panelErrorMessage(result.error, 'Nie udało się utworzyć linku.'),
        );
        return;
      }
      const created = result.data;
      const updated = {
        ...loadPanelKeys(),
        ...keys,
        [created.panel.panelId]: {
          linkKey: created.linkKey,
          expiresAt: created.panel.expiresAt,
        },
      };
      const stored = storePanelKeys(updated);
      setKeys(updated);
      setPanels((current) => [created.panel, ...current]);
      setLabel('');
      setNotice(
        stored
          ? 'Link utworzony. Wyślij odbiorcy cały link.'
          : 'Link utworzony. Skopiuj go teraz; przeglądarka nie zapamiętała linku.',
      );
    } catch {
      setError(
        'Nie potwierdzono utworzenia linku. Odśwież listę; zatrzymaj nieznany link przed utworzeniem następnego.',
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await client.revokeBoardSearchPanel(id);
      if (!result.data || result.error) {
        setError(
          panelErrorMessage(result.error, 'Nie udało się zatrzymać linku.'),
        );
        return;
      }
      const updated = Object.fromEntries(
        Object.entries(keys).filter(([panelId]) => panelId !== id),
      );
      storePanelKeys(updated);
      setKeys(updated);
      setConfirmId(null);
      setPanels((current) =>
        current.map((panel) => (panel.panelId === id ? result.data! : panel)),
      );
      setNotice('Dostęp do wszystkich gier tego linku został zatrzymany.');
    } catch {
      setError(
        'Nie potwierdzono zatrzymania. Odśwież listę i sprawdź status linku.',
      );
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setNotice('Link skopiowany.');
    } catch {
      setError('Nie udało się skopiować. Zaznacz cały link i skopiuj ręcznie.');
    }
  }
  return (
    <section className="sharingWorkspace" aria-label="Udostępnianie">
      <h1>Udostępnianie</h1>
      <p>
        Wybierz gry. Odbiorca otrzyma pełną wyszukiwarkę i możliwość poprawiania
        symboli. Każdy posiadacz linku ma ten dostęp.
      </p>
      {loading ? <p role="status">Wczytywanie gier i linków…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      <fieldset disabled={busy || loading}>
        <legend>Gry w nowym linku</legend>
        {games.length === 0 && !loading ? (
          <p>Brak aktywnych gier.</p>
        ) : (
          games.map((game) => (
            <label className="sharingGameOption" key={game.id}>
              <input
                type="checkbox"
                checked={selected.includes(game.id)}
                onChange={(event) =>
                  setSelected((current) =>
                    event.target.checked
                      ? [...current, game.id]
                      : current.filter((id) => id !== game.id),
                  )
                }
              />
              {game.name}
            </label>
          ))
        )}
        <label>
          Nazwa linku{' '}
          <input
            maxLength={100}
            value={label}
            onChange={(event) => setLabel(event.target.value)}
          />
        </label>
        <label>
          Ważność{' '}
          <select
            value={lifetime}
            onChange={(event) => setLifetime(Number(event.target.value))}
          >
            {BOARD_SEARCH_SHARE_LIFETIMES.map((choice) => (
              <option key={choice.minutes} value={choice.minutes}>
                {choice.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={selected.length === 0 || busy || loading}
          className="primaryButton"
          onClick={() => void create()}
        >
          {busy ? 'Zapisywanie…' : 'Utwórz link'}
        </button>
      </fieldset>
      <button
        type="button"
        disabled={busy || loading}
        onClick={() => void load()}
      >
        Odśwież linki
      </button>
      <h2>Linki</h2>
      {panels.length === 0 && !loading ? (
        <p>Nie utworzono jeszcze linków.</p>
      ) : null}
      {panels.map((panel) => {
        const url = panelShareUrl(panel.shareUrl, keys[panel.panelId]);
        const selectedLog =
          log?.panelId === panel.panelId
            ? panel.games.find((game) => game.sessionId === log.sessionId)
            : null;
        return (
          <article className="sharingLinkCard" key={panel.panelId}>
            <h3>{panel.label || 'Udostępnione gry'}</h3>
            <p>{panel.games.map((game) => game.gameName).join(', ')}</p>
            <p>
              {panel.status === 'active'
                ? 'Aktywny'
                : panel.status === 'expired'
                  ? 'Wygasły'
                  : 'Zatrzymany'}{' '}
              · do {formatBoardSearchShareDate(panel.expiresAt)}
            </p>
            {url ? (
              <>
                <input
                  aria-label="Link do panelu"
                  readOnly
                  value={url}
                  onFocus={(event) => event.target.select()}
                />
                <button type="button" onClick={() => void copy(url)}>
                  Kopiuj link
                </button>
              </>
            ) : panel.status === 'active' ? (
              <p>
                {panel.ready
                  ? 'Brak klucza w tej przeglądarce. Zatrzymaj link i utwórz nowy.'
                  : 'Tunel jest niedostępny. Po jego uruchomieniu odśwież linki.'}
              </p>
            ) : null}
            {panel.status === 'active' ? (
              confirmId === panel.panelId ? (
                <div>
                  <p>Zatrzymać dostęp do wszystkich gier tego linku?</p>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void revoke(panel.panelId)}
                  >
                    Potwierdź zatrzymanie
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setConfirmId(null)}
                  >
                    Anuluj
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setConfirmId(panel.panelId)}
                >
                  Zatrzymaj link
                </button>
              )
            ) : null}
            <label>
              Dziennik gry{' '}
              <select
                aria-label={`Dziennik gry ${panel.label || panel.panelId}`}
                value={selectedLog?.sessionId ?? ''}
                onChange={(event) =>
                  setLog(
                    event.target.value
                      ? {
                          panelId: panel.panelId,
                          sessionId: event.target.value,
                        }
                      : null,
                  )
                }
              >
                <option value="">Wybierz grę</option>
                {panel.games.map((game) => (
                  <option key={game.sessionId} value={game.sessionId}>
                    {game.gameName}
                  </option>
                ))}
              </select>
            </label>
            {selectedLog ? (
              <BoardSearchShareQueryLog
                key={selectedLog.sessionId}
                client={client}
                gameId={selectedLog.gameId}
                sessionId={selectedLog.sessionId}
                onReplay={onReplay}
              />
            ) : null}
          </article>
        );
      })}
    </section>
  );
}
