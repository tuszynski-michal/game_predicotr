'use client';

import type {
  AdminApiClient,
  ContentSessionResponse,
  ContentSessionStatus,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useRef, useState } from 'react';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import { GridContentCanvas } from './grid-content-canvas';
import {
  ContentCommandNotice,
  useContentCommands,
} from './grid-content-command-control';
import {
  emptyContentCells,
  type ContentCells,
  type ContentCommand,
  type ContentNodes,
} from './grid-content-state';

export type GridContentBlindClient = Pick<
  AdminApiClient,
  | 'listGridContentSessions'
  | 'getGridContentSession'
  | 'createGridContentSession'
  | 'writeGridBlindContentObservation'
  | 'advanceGridContentSession'
  | 'gridContentSessionSourceUrl'
>;

/** Deliberately receives a client without normal reference reads or model methods. */
export function GridContentBlind({
  api,
  apiBaseUrl,
  gameId,
  initialSessionId = '',
  children,
}: {
  readonly api: GridContentBlindClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly initialSessionId?: string;
  readonly children?: (
    create: (command: ContentCommand) => void,
    blocked: boolean,
  ) => React.ReactNode;
}) {
  const [sessions, setSessions] = useState<ContentSessionStatus[]>([]);
  const [session, setSession] = useState<ContentSessionResponse | null>(null);
  const [selected, setSelected] = useState(initialSessionId);
  const [targetIndex, setTargetIndex] = useState(0);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState('');
  const [notice, setNotice] = useState('');
  const [canvasEpoch, setCanvasEpoch] = useState(0);
  const [cells, setCells] = useState<ContentCells>(emptyContentCells);
  const [nodes, setNodes] = useState<ContentNodes | null>(null);
  const [ready, setReady] = useState(false);
  const [approved, setApproved] = useState(false);
  const sequence = useRef(0);
  const lock = useRef(false);
  const idRef = useRef(selected);
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      sequence.current += 1;
    };
  }, []);
  function reset() {
    setCanvasEpoch((v) => v + 1);
    setReady(false);
    setCells(emptyContentCells());
    setNodes(null);
    setApproved(false);
  }
  const load = useCallback(
    async (id: string) => {
      const token = ++sequence.current;
      idRef.current = id;
      setSelected(id);
      setSession(null);
      setReading(true);
      setReadError('');
      setCanvasEpoch((v) => v + 1);
      setReady(false);
      setCells(emptyContentCells());
      setNodes(null);
      setApproved(false);
      try {
        const result = await api.getGridContentSession(gameId, id);
        if (!alive.current || token !== sequence.current) return;
        if (!result.data)
          throw new Error(
            apiErrorMessage(result.error, 'Nie udało się odczytać sesji.'),
          );
        if (result.data.gameId !== gameId || result.data.sessionId !== id)
          throw new Error('Odrzucono sesję innej gry lub inny identyfikator.');
        setSession(result.data);
        setTargetIndex(
          Math.max(
            0,
            result.data.targets.findIndex((t) => !t.completed),
          ),
        );
      } catch (failure) {
        if (alive.current && token === sequence.current)
          setReadError(String(failure));
      } finally {
        if (alive.current && token === sequence.current) setReading(false);
      }
    },
    [api, gameId],
  );
  async function refreshList() {
    if (lock.current) return;
    lock.current = true;
    setReading(true);
    setReadError('');
    try {
      const result = await api.listGridContentSessions(gameId, 20);
      if (!alive.current) return;
      if (!result.data)
        throw new Error(
          apiErrorMessage(result.error, 'Nie udało się odczytać sesji.'),
        );
      if (result.data.items.some((s) => s.gameId !== gameId))
        throw new Error('Odrzucono sesje innej gry.');
      setSessions(result.data.items);
    } catch (failure) {
      if (alive.current) setReadError(String(failure));
    } finally {
      lock.current = false;
      if (alive.current) setReading(false);
    }
  }
  useEffect(() => {
    void Promise.resolve().then(() => {
      if (!alive.current) return;
      void refreshList();
      if (initialSessionId) void load(initialSessionId);
    });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  async function execute(command: ContentCommand) {
    if (command.kind === 'reference')
      throw new Error('Zwykłe etykiety nie są poleceniem ślepego pomiaru.');
    const result =
      command.kind === 'create'
        ? await api.createGridContentSession(gameId, command.body)
        : command.kind === 'observe'
          ? await api.writeGridBlindContentObservation(
              gameId,
              command.sessionId,
              command.body,
            )
          : command.kind === 'advance'
            ? await api.advanceGridContentSession(
                gameId,
                command.sessionId,
                command.body,
              )
            : null;
    if (!result?.data)
      throw new Error(
        apiErrorMessage(
          result?.error,
          'Nie potwierdzono polecenia ślepego pomiaru.',
        ),
      );
    if (
      result.data.idempotencyKey !== command.body.idempotencyKey ||
      result.data.session.gameId !== gameId ||
      (command.kind !== 'create' &&
        result.data.session.sessionId !== command.sessionId)
    )
      throw new Error('Odrzucono receipt innej komendy lub sesji.');
    if (alive.current) {
      setSessions((old) => [
        result.data!.session,
        ...old.filter((s) => s.sessionId !== result.data!.session.sessionId),
      ]);
      setNotice(
        'Potwierdzono zapis. Następny cel otwarto bez dawnych etykiet.',
      );
      await load(result.data.session.sessionId);
    }
  }
  const control = useContentCommands(apiBaseUrl, gameId, 'blind', execute);
  const target = session?.targets[targetIndex];
  const targetKey =
    target && session
      ? `${gameId}:${session.sessionId}:${session.phase}:${target.source.sourceId}:${target.source.sourceSha256}:${target.positionIndex}:${canvasEpoch}`
      : '';
  const editable =
    session &&
    session.phase !== 'frozen' &&
    target &&
    !target.completed &&
    Number.isInteger(target.sequenceNumber) &&
    target.sequenceNumber > 0;
  return (
    <section
      className="gridContentWorkflow"
      aria-label="Ślepy pomiar zawartości"
    >
      <h3>Dwa niezależne przebiegi pomiaru</h3>
      <p>
        Dwa przebiegi bez poprzednich etykiet i propozycji. Nie otwieraj
        zwykłych adnotacji w trakcie pomiaru. Każdy cel zaczyna od pustego
        obrazu.
      </p>
      <ContentCommandNotice control={control} />
      {notice ? <p role="status">{notice}</p> : null}
      {readError ? <p role="alert">{readError}</p> : null}
      <div className="gridContentActions">
        <button
          type="button"
          className="secondaryButton"
          disabled={reading || control.busy}
          aria-busy={reading}
          onClick={() => void refreshList()}
        >
          {reading ? 'Odczytywanie sesji…' : 'Odśwież listę sesji'}
        </button>
        <label>
          Sesja{' '}
          <select
            aria-label="Sesja ślepego pomiaru"
            value={selected}
            disabled={reading || control.busy}
            onChange={(e) => {
              if (e.target.value) void load(e.target.value);
              else {
                setSelected('');
                setSession(null);
                reset();
              }
            }}
          >
            <option value="">Wybierz sesję</option>
            {sessions.map((s, i) => (
              <option value={s.sessionId} key={s.sessionId}>
                Sesja {i + 1} ·{' '}
                {s.phase === 'pass1'
                  ? 'Przebieg 1'
                  : s.phase === 'pass2'
                    ? 'Przebieg 2'
                    : 'Zamrożona'}{' '}
                · {s.completed}/{s.total}
              </option>
            ))}
          </select>
        </label>
        {selected ? (
          <button
            className="secondaryButton"
            type="button"
            disabled={reading || control.busy}
            onClick={() => void load(selected)}
          >
            Odczytaj aktualny stan sesji
          </button>
        ) : null}
      </div>
      {!sessions.length && !reading ? (
        <p>
          Brak zapisanych sesji w ostatnich 20 wynikach. Możesz utworzyć nową
          lub podać identyfikator.
        </p>
      ) : null}
      <details>
        <summary>Zaawansowane: wznowienie po identyfikatorze</summary>
        <form
          className="gridContentActions"
          onSubmit={(event) => {
            event.preventDefault();
            if (idRef.current) void load(idRef.current);
          }}
        >
          <label>
            Identyfikator sesji do wznowienia{' '}
            <input
              aria-label="Identyfikator sesji do wznowienia"
              defaultValue={initialSessionId}
              onChange={(e) => {
                idRef.current = e.target.value;
              }}
            />
          </label>
          <button
            className="secondaryButton"
            disabled={reading || control.busy}
          >
            Wznów sesję po identyfikatorze
          </button>
        </form>
      </details>
      {!session && !reading
        ? children?.((command) => void control.send(command), control.blocked)
        : null}
      {session ? (
        <>
          <p>
            Bieżąca sesja.{' '}
            {session.phase === 'pass1'
              ? 'Przebieg 1'
              : session.phase === 'pass2'
                ? 'Przebieg 2'
                : 'Zamrożona'}
            . Ukończono {session.completed}/{session.total}; rewizja{' '}
            {session.revision}.
          </p>
          {session.phase !== 'frozen' ? (
            <>
              {!session.targets.length ? (
                <p>
                  Brak plansz w tej sesji. Odczytaj aktualny stan lub wybierz
                  inną sesję.
                </p>
              ) : null}
              <label>
                Cel pomiaru{' '}
                <select
                  aria-label="Cel ślepego pomiaru"
                  value={targetIndex}
                  disabled={control.busy || reading}
                  onChange={(e) => {
                    setTargetIndex(Number(e.target.value));
                    reset();
                  }}
                >
                  {session.targets.map((t, i) => (
                    <option
                      key={`${t.source.sourceId}:${t.positionIndex}`}
                      value={i}
                    >
                      Plansza {t.sequenceNumber} · pozycja {t.positionIndex + 1}
                      {t.completed ? ' · zapisano' : ''}
                    </option>
                  ))}
                </select>
              </label>
              {target?.completed ? (
                <p>
                  Ten cel jest zapisany. Poprzednie punkty i obwiednie pozostają
                  ukryte.
                </p>
              ) : null}
              {editable ? (
                <>
                  <GridContentCanvas
                    key={targetKey}
                    sourceUrl={api.gridContentSessionSourceUrl(
                      gameId,
                      session.sessionId,
                      target.source.sourceId,
                    )}
                    width={target.source.width}
                    height={target.source.height}
                    measureGeometry
                    disabled={control.blocked || reading}
                    onChange={(c, n, r) => {
                      setCells(c);
                      setNodes(n);
                      setReady(r);
                    }}
                  />
                  <label>
                    <input
                      type="checkbox"
                      checked={approved}
                      disabled={control.blocked}
                      onChange={(e) => setApproved(e.target.checked)}
                    />{' '}
                    Potwierdzam własny pomiar 24 punktów i 15 pól w tym
                    przebiegu
                  </label>
                  <button
                    className="primaryButton"
                    type="button"
                    disabled={control.blocked || !ready || !nodes || !approved}
                    onClick={() => {
                      if (!nodes || !ready || !approved) return;
                      void control.send({
                        kind: 'observe',
                        sessionId: session.sessionId,
                        body: {
                          idempotencyKey: crypto.randomUUID(),
                          expectedSessionRevision: session.revision,
                          passNumber: session.phase === 'pass1' ? 1 : 2,
                          sourceId: target.source.sourceId,
                          positionIndex: target.positionIndex,
                          cells,
                          measuredNodes: nodes,
                          humanApproval: true,
                        },
                      });
                    }}
                  >
                    Zapisz ślepy pomiar i dalej
                  </button>
                </>
              ) : null}
              <button
                className="primaryButton"
                type="button"
                disabled={
                  control.blocked ||
                  reading ||
                  session.completed !== session.total ||
                  session.total === 0
                }
                onClick={() =>
                  void control.send({
                    kind: 'advance',
                    sessionId: session.sessionId,
                    body: {
                      idempotencyKey: crypto.randomUUID(),
                      expectedSessionRevision: session.revision,
                    },
                  })
                }
              >
                {session.phase === 'pass1'
                  ? 'Zamknij przebieg 1 i rozpocznij pusty przebieg 2'
                  : 'Zamroź pomiar i sprawdź powtarzalność'}
              </button>
            </>
          ) : (
            <>
              <p>
                Pomiar zamrożony. Nie oznacza to kwalifikacji modelu ani
                automatu. Wynik obejmuje wyłącznie tę sesję i grę.
              </p>
              <details>
                <summary>Wynik powtarzalności i oracle</summary>
                <pre>{JSON.stringify(session.report, null, 2)}</pre>
              </details>
            </>
          )}
        </>
      ) : null}
    </section>
  );
}
