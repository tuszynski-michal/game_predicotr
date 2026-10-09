'use client';

import type {
  ManagementStake,
  ManagementStakeResponse,
  ManagementRefreshCommand,
} from '@game-predictor/admin-api-client';
import {
  BoardSearchWorkspace,
  confirmBoardSearchDiscardDraft,
  type BoardSearchDraft,
  type BoardSearchSavedSelection,
} from '../index';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  type ManagementGameClient,
  managementError,
  managementSessionStorage,
} from './management-client';
import { ManagementCards } from './management-cards';
import { ManagementJournal } from './management-journal';
import { ManagementResultView } from './management-result-view';
import {
  createManagementDataSource,
  managementSlotFor,
} from './management-data-source';
import {
  ManagementSlotRecovery,
  ManagementMutationError,
} from './management-slot-operation';
import {
  applyManagementRefresh,
  managementSavedSelection,
  refreshManagementQueue,
  type ManagementCardState,
} from './management-slot-state';

type Editor = {
  stake: ManagementStake;
  generation: number;
  initial: BoardSearchSavedSelection | null;
  expectedRevision: number;
};
type ResultView = {
  versionId: string;
  stake: ManagementStake;
  historical: boolean;
  pins: readonly number[];
};

export function ManagementGameWorkspace({
  api,
  machineId,
  gameId,
  writeAllowed,
  accessAllowed = true,
  storageNamespace = 'local-owner',
  onDirtyChange,
  pauseRefresh = false,
  selectedStake,
  onStakeSelected,
}: {
  api: ManagementGameClient;
  machineId: string;
  gameId: string;
  writeAllowed: boolean;
  accessAllowed?: boolean;
  storageNamespace?: string;
  onDirtyChange?: (dirty: boolean) => void;
  pauseRefresh?: boolean;
  selectedStake?: number | null;
  onStakeSelected?: (stake: ManagementStake) => void;
}) {
  const mutationAllowed = writeAllowed && accessAllowed;
  const [cards, setCards] = useState<readonly ManagementCardState[]>([]);
  const cardsRef = useRef(cards);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const [pendingRevision, setPendingRevision] = useState(0);
  const [journalRevision, setJournalRevision] = useState(0);
  const [editor, setEditor] = useState<Editor | null>(null);
  const editorRef = useRef(editor);
  const [view, setView] = useState<ResultView | null>(null);
  const dirty = useRef(false);
  const mounted = useRef(true);
  const allowedRef = useRef(writeAllowed);
  allowedRef.current = writeAllowed && accessAllowed;
  const accessRef = useRef(accessAllowed);
  accessRef.current = accessAllowed;
  const listId = useRef(0);
  const controllers = useRef(new Set<AbortController>());
  const refreshController = useRef<AbortController | null>(null);
  const pauseRefreshRef = useRef(pauseRefresh);
  pauseRefreshRef.current = pauseRefresh;
  useEffect(() => {
    if (pauseRefresh) refreshController.current?.abort();
  }, [pauseRefresh]);
  const storage = managementSessionStorage();
  const recovery = useMemo(
    () =>
      new ManagementSlotRecovery(
        storage,
        storageNamespace,
        () => {
          if (mounted.current) setPendingRevision((value) => value + 1);
        },
        () => mounted.current && accessRef.current,
      ),
    [storage, storageNamespace],
  );
  const pending = recovery.pending;
  const pendingHere =
    pending?.machineId === machineId && pending.gameId === gameId;
  const refreshRef = useRef<() => void>(() => {});
  const callbacks = useRef({ onDirtyChange });
  callbacks.current = { onDirtyChange };
  const updateCards = useCallback(
    (
      change: (
        current: readonly ManagementCardState[],
      ) => readonly ManagementCardState[],
    ) => {
      if (!mounted.current) return;
      const next = change(cardsRef.current);
      cardsRef.current = next;
      setCards(next);
    },
    [],
  );
  const setDirty = useCallback((value: boolean) => {
    dirty.current = value;
    callbacks.current.onDirtyChange?.(value);
  }, []);
  const resyncSlot = useCallback(
    async (stake: ManagementStake, conflict: boolean) => {
      if (!accessRef.current) return;
      const controller = new AbortController();
      controllers.current.add(controller);
      const expected = managementSlotFor(cardsRef.current, stake);
      try {
        const response = await api.getManagementStake(
          machineId,
          gameId,
          stake,
          controller.signal,
        );
        if (!mounted.current || controller.signal.aborted) return;
        if (!response.data || response.error !== undefined)
          throw new Error(
            managementError(
              response.error,
              'Nie udało się odświeżyć rewizji zapisu.',
            ),
          );
        const slot = response.data;
        let accepted = !expected;
        if (expected) {
          const previous = cardsRef.current;
          const next = applyManagementRefresh(previous, expected, {
            slot,
            status: slot.empty ? 'empty' : 'stale',
            error: slot.staleErrorCode ?? undefined,
          });
          accepted = next.some((card, index) => card !== previous[index]);
          updateCards(() => next);
        }
        if (accepted && conflict && editorRef.current?.stake === stake) {
          editorRef.current = {
            ...editorRef.current,
            expectedRevision: slot.revision,
          };
          setEditor(editorRef.current);
        }
        if (conflict)
          setNotice(
            'Zapis zmienił się w innym oknie. Odświeżono jego rewizję. Twój szkic pozostał zachowany; sprawdź go przed kolejnym zapisem.',
          );
      } catch (cause) {
        if (mounted.current && !controller.signal.aborted)
          setError(managementError(cause, 'Nie udało się odświeżyć zapisu.'));
      } finally {
        controllers.current.delete(controller);
      }
    },
    [api, machineId, gameId, updateCards],
  );

  const refresh = useCallback(
    async (items: readonly ManagementStakeResponse[]) => {
      refreshController.current?.abort();
      const controller = new AbortController();
      refreshController.current = controller;
      if (
        pauseRefreshRef.current ||
        !accessRef.current ||
        !allowedRef.current ||
        recovery.pending ||
        recovery.readError
      )
        return;
      await refreshManagementQueue(
        items.filter((slot) => !slot.empty),
        controller.signal,
        async (expected) => {
          if (
            pauseRefreshRef.current ||
            !accessRef.current ||
            controller.signal.aborted ||
            !mounted.current ||
            recovery.pending
          )
            return;
          updateCards((current) =>
            applyManagementRefresh(current, expected, {
              slot: expected,
              status: 'checking',
            }),
          );
          const key = `game-predictor:management:refresh:${storageNamespace}:${machineId}:${gameId}:${expected.stakeGrosze}:v1`;
          let body: ManagementRefreshCommand;
          try {
            const raw = storage?.getItem(key);
            const restored: unknown = raw ? JSON.parse(raw) : null;
            if (
              restored !== null &&
              (!restored ||
                typeof restored !== 'object' ||
                !('operationId' in restored) ||
                typeof restored.operationId !== 'string' ||
                !('expectedRevision' in restored) ||
                typeof restored.expectedRevision !== 'number')
            )
              throw new Error('Nieprawidłowa oczekująca operacja odświeżenia.');
            body = (restored as ManagementRefreshCommand | null) ?? {
              operationId: crypto.randomUUID(),
              expectedRevision: expected.revision,
            };
            if (!storage)
              throw new Error('Brak pamięci sesji do zachowania odświeżenia.');
            storage.setItem(key, JSON.stringify(body));
            const response = await api.refreshManagementStake(
              machineId,
              gameId,
              expected.stakeGrosze,
              body,
              controller.signal,
            );
            if (!accessRef.current) return;
            if (response.data && response.error === undefined)
              storage.removeItem(key);
            else if (
              response.response &&
              response.response.status >= 400 &&
              response.response.status < 500 &&
              ![401, 403, 429].includes(response.response.status)
            )
              storage.removeItem(key);
            if (!mounted.current || controller.signal.aborted) return;
            if (!response.data || response.error !== undefined) {
              if (response.response?.status === 409) {
                await resyncSlot(expected.stakeGrosze, false);
                return;
              }
              throw new Error(
                managementError(
                  response.error,
                  'Nie udało się sprawdzić bieżących danych.',
                ),
              );
            }
            const data = response.data;
            const previous = cardsRef.current;
            const next = applyManagementRefresh(previous, expected, {
              slot: data.slot,
              status: data.status,
              error: data.errorCode ?? undefined,
            });
            const accepted = next.some(
              (card, index) => card !== previous[index],
            );
            updateCards(() => next);
            if (
              !accepted &&
              data.slot.revision <
                (managementSlotFor(cardsRef.current, expected.stakeGrosze)
                  ?.revision ?? 0)
            ) {
              await resyncSlot(expected.stakeGrosze, false);
              if (mounted.current && !controller.signal.aborted)
                setNotice(
                  'Potwierdzono wcześniejsze odświeżenie. Nowszy zapis pozostaje zachowany; odśwież go, aby sprawdzić bieżące dane.',
                );
            }
            if (data.changed) setJournalRevision((value) => value + 1);
            if (accepted)
              setView((current) =>
                current &&
                !current.historical &&
                current.stake === expected.stakeGrosze &&
                data.slot.resultVersionId
                  ? {
                      ...current,
                      versionId: data.slot.resultVersionId,
                      pins: data.slot.pinnedSpinPositions ?? [],
                    }
                  : current,
              );
          } catch (cause) {
            if (mounted.current && !controller.signal.aborted)
              updateCards((current) =>
                applyManagementRefresh(current, expected, {
                  slot: expected,
                  status: 'stale',
                  error: managementError(
                    cause,
                    'Nie udało się sprawdzić bieżących danych.',
                  ),
                }),
              );
          }
        },
      );
    },
    [
      api,
      machineId,
      gameId,
      storageNamespace,
      recovery,
      storage,
      updateCards,
      resyncSlot,
    ],
  );
  refreshRef.current = () => {
    void refresh(cardsRef.current.map((card) => card.slot));
  };

  const load = useCallback(async () => {
    if (!accessRef.current) return;
    const id = ++listId.current;
    const controller = new AbortController();
    controllers.current.add(controller);
    setLoading(true);
    setError('');
    try {
      const response = await api.listManagementStakes(
        machineId,
        gameId,
        controller.signal,
      );
      if (
        !mounted.current ||
        controller.signal.aborted ||
        id !== listId.current
      )
        return;
      if (!response.data || response.error !== undefined)
        throw new Error(
          managementError(
            response.error,
            'Nie udało się wczytać zapisanych stawek.',
          ),
        );
      const data = response.data;
      updateCards((current) =>
        data.slots.map((slot) => {
          const previous = current.find(
            (card) => card.slot.stakeGrosze === slot.stakeGrosze,
          );
          return previous && previous.slot.revision > slot.revision
            ? previous
            : {
                slot,
                status: slot.empty
                  ? 'empty'
                  : slot.staleErrorCode || !writeAllowed
                    ? 'stale'
                    : 'checking',
                error: slot.staleErrorCode ?? undefined,
              };
        }),
      );
      void refresh(cardsRef.current.map((card) => card.slot));
    } catch (cause) {
      if (
        mounted.current &&
        !controller.signal.aborted &&
        id === listId.current
      )
        setError(
          managementError(cause, 'Nie udało się wczytać zapisanych stawek.'),
        );
    } finally {
      controllers.current.delete(controller);
      if (mounted.current && id === listId.current) setLoading(false);
    }
  }, [api, machineId, gameId, updateCards, refresh, writeAllowed]);
  const cancelReads = useCallback(() => {
    ++listId.current;
    refreshController.current?.abort();
    for (const controller of controllers.current) controller.abort();
  }, []);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      cancelReads();
      callbacks.current.onDirtyChange?.(false);
    };
  }, [cancelReads]);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active && accessAllowed) void load();
    });
    return () => {
      active = false;
      cancelReads();
    };
  }, [load, cancelReads, accessAllowed]);

  const commitSlot = (slot: ManagementStakeResponse) => {
    const observed = managementSlotFor(cardsRef.current, slot.stakeGrosze);
    if (
      slot.machineId !== machineId ||
      slot.gameId !== gameId ||
      (observed && slot.revision < observed.revision)
    )
      return;
    updateCards((current) =>
      current.map((card) =>
        card.slot.stakeGrosze === slot.stakeGrosze &&
        slot.revision >= card.slot.revision
          ? { slot, status: slot.empty ? 'empty' : 'current' }
          : card,
      ),
    );
    setView((current) =>
      current && !current.historical && current.stake === slot.stakeGrosze
        ? slot.resultVersionId
          ? {
              ...current,
              versionId: slot.resultVersionId,
              pins: slot.pinnedSpinPositions ?? [],
            }
          : null
        : current,
    );
    setJournalRevision((value) => value + 1);
  };
  const prepareEditor = (stake: ManagementStake) => {
    if (
      !allowedRef.current ||
      recovery.pending ||
      !confirmBoardSearchDiscardDraft(dirty.current)
    )
      return;
    const slot = managementSlotFor(cardsRef.current, stake);
    if (!slot) return;
    onStakeSelected?.(stake);
    try {
      const next = {
        stake,
        generation: (editorRef.current?.generation ?? 0) + 1,
        initial: managementSavedSelection(slot),
        expectedRevision: slot.revision,
      };
      editorRef.current = next;
      setEditor(next);
      setDirty(false);
      setError('');
    } catch (cause) {
      setError(managementError(cause, 'Nie udało się otworzyć układu.'));
    }
  };
  const onCommitted = useCallback(() => {
    if (!mounted.current || !accessRef.current) return;
    setJournalRevision((value) => value + 1);
    refreshRef.current();
  }, []);
  const editorIdentity = editor ? `${editor.stake}:${editor.generation}` : null;
  const editorSource = useMemo(() => {
    if (editorIdentity === null) return null;
    const opened = editorRef.current;
    return opened
      ? createManagementDataSource({
          api,
          machineId,
          gameId,
          stake: opened.stake,
          recovery,
          initialSearchContextId: opened.initial?.searchContextId,
          getRevision: () =>
            editorRef.current?.expectedRevision ?? opened.expectedRevision,
          onCommitted,
          onSearchCommitted: () => {
            if (mounted.current) setJournalRevision((value) => value + 1);
          },
          canWrite: () => mounted.current && allowedRef.current,
          canAccess: () => mounted.current && accessRef.current,
          writeAllowed,
          onConflict: () => {
            void resyncSlot(opened.stake, true);
          },
        })
      : null;
  }, [
    api,
    machineId,
    gameId,
    editorIdentity,
    recovery,
    onCommitted,
    resyncSlot,
    writeAllowed,
  ]);
  const resultStake = view?.stake;
  const resultSource = useMemo(
    () =>
      resultStake !== undefined && writeAllowed
        ? createManagementDataSource({
            api,
            machineId,
            gameId,
            stake: resultStake,
            recovery,
            getRevision: () =>
              managementSlotFor(cardsRef.current, resultStake)?.revision ?? 0,
            onCommitted,
            canWrite: () => mounted.current && allowedRef.current,
            canAccess: () => mounted.current && accessRef.current,
            onConflict: () => {
              void resyncSlot(resultStake, false);
            },
          })
        : null,
    [
      api,
      machineId,
      gameId,
      resultStake,
      writeAllowed,
      recovery,
      onCommitted,
      resyncSlot,
    ],
  );
  useEffect(() => () => editorSource?.abort(), [editorSource]);
  useEffect(() => () => resultSource?.abort(), [resultSource]);
  const save = async (draft: BoardSearchDraft) => {
    const opened = editorRef.current;
    if (
      !opened ||
      !allowedRef.current ||
      draft.startSequenceNumber === null ||
      draft.searchContextId === null
    )
      throw new Error('Brak planszy do zapisania.');
    const operation = {
      kind: 'save' as const,
      machineId,
      gameId,
      stake: opened.stake,
      body: {
        operationId: crypto.randomUUID(),
        expectedRevision: opened.expectedRevision,
        searchContextId: draft.searchContextId,
        startSequenceNumber: draft.startSequenceNumber,
        spinCount: draft.spinCount,
        pinnedSpinPositions: [...draft.pinnedSpinPositions],
      },
    };
    try {
      const slot = await recovery.run(operation, () =>
        api.saveManagementStake(
          machineId,
          gameId,
          opened.stake,
          operation.body,
        ),
      );
      if (!mounted.current) return;
      commitSlot(slot);
      if (editorRef.current?.generation === opened.generation) {
        editorRef.current = { ...opened, expectedRevision: slot.revision };
        setEditor(editorRef.current);
      }
      setNotice('Zapisano układ tej stawki.');
    } catch (cause) {
      if (cause instanceof ManagementMutationError && cause.conflict)
        await resyncSlot(opened.stake, true);
      throw cause;
    }
  };
  const clear = async (stake: ManagementStake) => {
    if (
      !allowedRef.current ||
      recovery.pending ||
      busyRef.current ||
      !confirmBoardSearchDiscardDraft(dirty.current)
    )
      return;
    const slot = managementSlotFor(cardsRef.current, stake);
    if (
      !slot ||
      slot.empty ||
      !window.confirm(
        'Wyczyścić tylko tę stawkę? Plansze i dziennik pozostaną zachowane.',
      )
    )
      return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    const operation = {
      kind: 'clear' as const,
      machineId,
      gameId,
      stake,
      body: {
        operationId: crypto.randomUUID(),
        expectedRevision: slot.revision,
        confirmed: true as const,
      },
    };
    try {
      const data = await recovery.run(operation, () =>
        api.clearManagementStake(machineId, gameId, stake, operation.body),
      );
      if (!mounted.current) return;
      commitSlot(data);
      editorRef.current = null;
      setEditor(null);
      setDirty(false);
      setView((current) =>
        current?.stake === stake && !current.historical ? null : current,
      );
      setNotice('Wyczyszczono tę stawkę. Historia pozostaje zachowana.');
    } catch (cause) {
      if (mounted.current) {
        setError(managementError(cause, 'Nieznany wynik wyczyszczenia.'));
        if (cause instanceof ManagementMutationError && cause.conflict)
          await resyncSlot(stake, true);
      }
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  const retry = async () => {
    const operation = recovery.pending;
    if (!accessRef.current || !operation || !pendingHere || busyRef.current)
      return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      if (operation.kind === 'save') {
        const slot = await recovery.run(operation, () =>
          api.saveManagementStake(
            machineId,
            gameId,
            operation.stake,
            operation.body,
          ),
        );
        if (mounted.current) {
          commitSlot(slot);
          const opened = editorRef.current;
          if (
            opened?.stake === operation.stake &&
            opened.expectedRevision === operation.body.expectedRevision
          ) {
            editorRef.current = { ...opened, expectedRevision: slot.revision };
            setEditor(editorRef.current);
          }
        }
      } else if (operation.kind === 'clear') {
        const slot = await recovery.run(operation, () =>
          api.clearManagementStake(
            machineId,
            gameId,
            operation.stake,
            operation.body,
          ),
        );
        if (mounted.current) commitSlot(slot);
      } else if (operation.kind === 'search') {
        await recovery.run(operation, () =>
          api.searchManagementBoards(machineId, gameId, operation.body),
        );
        if (mounted.current) setJournalRevision((value) => value + 1);
      } else {
        await recovery.run(operation, () =>
          api.correctManagementBoardCell(
            machineId,
            gameId,
            operation.stake,
            operation.sequence,
            operation.cell,
            operation.body,
          ),
        );
        if (mounted.current) onCommitted();
      }
      if (mounted.current)
        setNotice(
          'Potwierdzono poprzednią operację. Bieżący szkic pozostaje zachowany; zapisz go osobno po sprawdzeniu.',
        );
    } catch (cause) {
      if (mounted.current) {
        setError(managementError(cause, 'Wynik zapisu pozostaje nieznany.'));
        if (cause instanceof ManagementMutationError && cause.conflict)
          await resyncSlot(operation.stake, true);
      }
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  // Reading history does not navigate away from or replace an open draft.
  const open = (stake: ManagementStake) => {
    if (!accessRef.current) return;
    const slot = managementSlotFor(cardsRef.current, stake);
    onStakeSelected?.(stake);
    if (slot?.resultVersionId)
      setView({
        stake,
        versionId: slot.resultVersionId,
        historical: false,
        pins: slot.pinnedSpinPositions ?? [],
      });
  };
  return (
    <section
      aria-label="Zapisane stawki"
      data-pending-revision={pendingRevision}
    >
      {!writeAllowed && accessAllowed ? (
        <p className="feedbackBanner">
          Archiwalna lub odłączona gra. Zapisane wyniki i historia są dostępne
          tylko do odczytu.
        </p>
      ) : null}
      <div className="management-actions">
        <button
          disabled={loading || busy || !accessAllowed}
          onClick={() => void load()}
        >
          Odśwież zapisane stawki
        </button>
      </div>
      {loading ? <p role="status">Wczytywanie zapisanych stawek…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {pending ? (
        <div className="feedbackBanner">
          <p>
            Nieznany wynik ostatniej operacji. Zapis mógł już zostać
            zatwierdzony. Nowe operacje są zablokowane do sprawdzenia.
          </p>
          {pendingHere ? (
            <button
              disabled={busy || !accessAllowed}
              onClick={() => void retry()}
            >
              Sprawdź ostatni zapis stawki
            </button>
          ) : (
            <p>Wróć do maszyny i gry poprzedniej operacji.</p>
          )}
        </div>
      ) : null}
      {recovery.readError ? (
        <p role="alert">{recovery.readError} Nowe zapisy są zablokowane.</p>
      ) : null}
      <ManagementCards
        cards={cards}
        writeAllowed={mutationAllowed}
        busy={
          !accessAllowed ||
          busy ||
          pending !== null ||
          recovery.readError !== null
        }
        onOpen={open}
        onSearch={prepareEditor}
        onClear={(stake) => void clear(stake)}
        selectedStake={selectedStake}
      />
      {selectedStake ? (
        <p>
          Wybrana stawka: {(selectedStake / 100).toLocaleString('pl-PL')} zł
        </p>
      ) : null}
      {editor && editorSource ? (
        <fieldset
          disabled={!accessAllowed}
          className="management-draft"
          aria-label="Szkic układu"
        >
          <h3>
            Szkic dla stawki {(editor.stake / 100).toLocaleString('pl-PL')} zł
          </h3>
          <button
            onClick={() => {
              if (!confirmBoardSearchDiscardDraft(dirty.current)) return;
              editorRef.current = null;
              setEditor(null);
              setDirty(false);
            }}
          >
            Zamknij szkic
          </button>
          <p>
            Poprawianie symboli zapisuje od razu bieżące dane gry. Wybór
            planszy, zakres i punkty zapisujesz przyciskiem „Zapisz układ”.
          </p>
          <BoardSearchWorkspace
            client={editorSource.client}
            gameId={gameId}
            scopeKey={`${machineId}:${gameId}:${editor.stake}:${editor.generation}`}
            fixedStakeGrosze={editor.stake}
            savedSelection={editor.initial}
            onDirtyChange={setDirty}
            onSave={mutationAllowed ? save : undefined}
          />
        </fieldset>
      ) : null}
      {view ? (
        <ManagementResultView
          key={view.versionId}
          api={api}
          machineId={machineId}
          gameId={gameId}
          versionId={view.versionId}
          stake={view.stake}
          historical={view.historical}
          pins={view.pins}
          boardClient={resultSource?.client}
          writeAllowed={mutationAllowed}
        />
      ) : null}
      <ManagementJournal
        api={api}
        machineId={machineId}
        gameId={gameId}
        revision={journalRevision}
        accessAllowed={accessAllowed}
        onHistory={(versionId, stake, pins) =>
          accessRef.current &&
          setView({ versionId, stake, pins, historical: true })
        }
      />
    </section>
  );
}
