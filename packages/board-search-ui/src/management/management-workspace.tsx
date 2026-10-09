'use client';

import type {
  ManagementPointResponse,
  ManagementMachineResponse,
  ManagementSnapshotResponse,
  ManagementMachineCommand,
  ManagementMutationCounts,
} from '@game-predictor/admin-api-client';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from 'react';
import {
  executeManagementOperation,
  readManagementOperation,
  managementPendingKey,
  type ManagementOperation,
} from './management-operation';
import { confirmBoardSearchDiscardDraft } from '../index';
import {
  type ManagementGameClient,
  type ManagementStructureClient,
  managementSessionStorage,
} from './management-client';
import { ManagementGameWorkspace } from './management-game-workspace';
import {
  managementSlotWritesAllowed,
  managementSlotsAvailable,
} from './management-data-source';
import { readManagementSlotOperation } from './management-slot-operation';
import {
  ManagementStructureModal,
  type ManagementStructureEditor,
} from './management-structure-modal';
import {
  managementLocationFromUrl,
  managementUrlWithLocation,
  sameManagementLocation,
  validManagementLocation,
  type ManagementLocation,
} from './management-navigation';

export type ManagementClient = ManagementStructureClient &
  Partial<ManagementGameClient>;

interface Props {
  client: ManagementClient;
  gameClientForMachine?: (machineId: string) => ManagementGameClient;
  headerActions?: ReactNode;
  accessAllowed?: boolean;
  storageNamespace?: string;
  onDirtyChange?: (dirty: boolean) => void;
}
type Editor = (ManagementStructureEditor & { baseRevision: number }) | null;

export function ManagementWorkspace({
  client: api,
  gameClientForMachine,
  headerActions,
  accessAllowed = true,
  storageNamespace = 'local-owner',
  onDirtyChange,
}: Props) {
  const accessRef = useRef(accessAllowed);
  const mounted = useRef(true);
  useLayoutEffect(() => {
    accessRef.current = accessAllowed;
  }, [accessAllowed]);
  useLayoutEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const pendingKey = managementPendingKey(storageNamespace);
  const [snapshot, setSnapshot] = useState<ManagementSnapshotResponse | null>(
    null,
  );
  const snapshotScope = useRef(storageNamespace);
  const restoredScopeKey = useRef<string | null>(null);
  const previousNamespace = useRef(storageNamespace);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const loadGeneration = useRef(0);
  const [location, setLocation] = useState<ManagementLocation>(() =>
    typeof window === 'undefined'
      ? { pointId: null, machineId: null, gameId: null, stake: null }
      : managementLocationFromUrl(window.location.search),
  );
  const locationRef = useRef(location);
  const outerNavigationCancelled = useRef(false);
  useLayoutEffect(() => {
    locationRef.current = location;
  }, [location]);
  const machineId = location.machineId;
  const gameId = location.gameId;
  const draftDirty = useRef(false);
  const modalDirtyRef = useRef(false);
  const changeDirty = useCallback(
    (dirty: boolean) => {
      draftDirty.current = dirty;
      onDirtyChange?.(dirty || modalDirtyRef.current);
    },
    [onDirtyChange],
  );
  const [editor, setEditor] = useState<Editor>(null);
  const editorRef = useRef<Editor>(null);
  const [editorConflict, setEditorConflict] = useState(false);
  useLayoutEffect(() => {
    editorRef.current = editor;
  }, [editor]);
  const [name, setName] = useState('');
  const nameInput = useRef<HTMLInputElement>(null);
  const [city, setCity] = useState('');
  const [street, setStreet] = useState('');
  const [gameIds, setGameIds] = useState<string[]>([]);
  const [editorInitial, setEditorInitial] = useState('');
  const modalDirty =
    editor !== null &&
    editorInitial !== modalSignature(name, city, street, gameIds);
  useLayoutEffect(() => {
    modalDirtyRef.current = modalDirty;
  }, [modalDirty]);
  useEffect(() => {
    onDirtyChange?.(draftDirty.current || modalDirty);
  }, [modalDirty, onDirtyChange]);
  const navigationAllowed = useCallback(
    () => confirmBoardSearchDiscardDraft(draftDirty.current || modalDirty),
    [modalDirty],
  );
  const [confirming, setConfirming] = useState(false);
  const [deleteTarget, setDeleteTarget] =
    useState<ManagementStructureEditor | null>(null);
  const [deleteCounts, setDeleteCounts] =
    useState<ManagementMutationCounts | null>(null);
  const [deleteToken, setDeleteToken] = useState('');
  const [deleteRevision, setDeleteRevision] = useState(0);
  const [notice, setNotice] = useState('');
  // Keep the exact command after uncertain network failures; retry must use its UUID.
  const pending = useRef<ManagementOperation | null>(null);
  const [retryAvailable, setRetryAvailable] = useState(false);
  useLayoutEffect(() => {
    if (previousNamespace.current === storageNamespace) return;
    previousNamespace.current = storageNamespace;
    pending.current = null;
    restoredScopeKey.current = null;
    draftDirty.current = false;
    modalDirtyRef.current = false;
    setRetryAvailable(false);
    setSnapshot(null);
    setEditor(null);
    setDeleteTarget(null);
    onDirtyChange?.(false);
  }, [storageNamespace, onDirtyChange]);

  const load = useCallback(
    async (preserveError = false) => {
      if (!mounted.current || !accessRef.current) return;
      const generation = ++loadGeneration.current;
      setLoading(true);
      try {
        const response = await api.getManagementSnapshot();
        if (
          !mounted.current ||
          !accessRef.current ||
          generation !== loadGeneration.current
        )
          return;
        if (!response.data) throw new Error('Nie udało się pobrać punktów.');
        snapshotScope.current = storageNamespace;
        setSnapshot(response.data);
        const opened = editorRef.current;
        if (
          opened &&
          (opened.kind === 'point' ? opened.point : opened.machine)
        ) {
          const freshPoint = response.data.points.find(
            (item) =>
              item.id ===
              (opened.kind === 'point' ? opened.point?.id : opened.point.id),
          );
          const freshRevision =
            opened.kind === 'point'
              ? freshPoint?.revision
              : freshPoint?.machines.find(
                  (item) => item.id === opened.machine?.id,
                )?.revision;
          if (
            freshRevision === undefined ||
            freshRevision !== opened.baseRevision
          )
            setEditorConflict(true);
        }
        const valid = validManagementLocation(
          locationRef.current,
          response.data,
        );
        if (!sameManagementLocation(valid, locationRef.current)) {
          locationRef.current = valid;
          setLocation(valid);
          window.history.replaceState(
            null,
            '',
            managementUrlWithLocation(window.location.href, valid),
          );
        }
        if (!preserveError) setError('');
      } catch (cause) {
        if (generation === loadGeneration.current)
          setError(cause instanceof Error ? cause.message : 'Błąd API.');
      } finally {
        if (generation === loadGeneration.current) setLoading(false);
      }
    },
    [api, storageNamespace],
  );
  const invalidateLoad = useCallback(() => {
    ++loadGeneration.current;
  }, []);
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) void load();
    });
    return () => {
      cancelled = true;
      invalidateLoad();
    };
  }, [load, invalidateLoad]);

  useEffect(() => {
    const onFocus = () => {
      void load();
    };
    window.addEventListener('focus', onFocus);
    return () => window.removeEventListener('focus', onFocus);
  }, [load]);

  const navigate = (next: ManagementLocation, replace = false) => {
    if (!accessRef.current || !navigationAllowed()) return false;
    try {
      window.sessionStorage.setItem(
        `game-predictor:management:scroll:${storageNamespace}:${locationRef.current.pointId ?? 'home'}:${locationRef.current.machineId ?? 'points'}`,
        String(window.scrollY),
      );
    } catch {
      /* Scroll position is optional. */
    }
    changeDirty(false);
    setEditor(null);
    setDeleteTarget(null);
    locationRef.current = next;
    setLocation(next);
    window.history[replace ? 'replaceState' : 'pushState'](
      null,
      '',
      managementUrlWithLocation(window.location.href, next),
    );
    try {
      const stored = window.sessionStorage.getItem(
        `game-predictor:management:scroll:${storageNamespace}:${next.pointId ?? 'home'}:${next.machineId ?? 'points'}`,
      );
      window.requestAnimationFrame?.(() =>
        window.scrollTo(0, stored ? Number(stored) || 0 : 0),
      );
    } catch {
      /* Optional scroll restoration. */
    }
    if (!next.machineId) void load();
    return true;
  };
  useEffect(() => {
    const onOuterCancel = () => {
      outerNavigationCancelled.current = true;
      queueMicrotask(() => {
        outerNavigationCancelled.current = false;
      });
    };
    window.addEventListener(
      'management:outer-navigation-cancelled',
      onOuterCancel,
    );
    return () =>
      window.removeEventListener(
        'management:outer-navigation-cancelled',
        onOuterCancel,
      );
  }, []);
  useEffect(() => {
    const onPop = () => {
      if (outerNavigationCancelled.current) {
        outerNavigationCancelled.current = false;
        window.history.replaceState(
          null,
          '',
          managementUrlWithLocation(window.location.href, locationRef.current),
        );
        return;
      }
      if (
        new URLSearchParams(window.location.search).get('workspace') !==
        'management'
      )
        return;
      const next = snapshot
        ? validManagementLocation(
            managementLocationFromUrl(window.location.search),
            snapshot,
          )
        : managementLocationFromUrl(window.location.search);
      if (sameManagementLocation(next, locationRef.current)) return;
      if (!navigationAllowed()) {
        window.history.pushState(
          null,
          '',
          managementUrlWithLocation(window.location.href, locationRef.current),
        );
        return;
      }
      changeDirty(false);
      setEditor(null);
      setDeleteTarget(null);
      try {
        window.sessionStorage.setItem(
          `game-predictor:management:scroll:${storageNamespace}:${locationRef.current.pointId ?? 'home'}:${locationRef.current.machineId ?? 'points'}`,
          String(window.scrollY),
        );
      } catch {
        /* Optional scroll position. */
      }
      locationRef.current = next;
      setLocation(next);
      window.history.replaceState(
        null,
        '',
        managementUrlWithLocation(window.location.href, next),
      );
      try {
        const stored = window.sessionStorage.getItem(
          `game-predictor:management:scroll:${storageNamespace}:${next.pointId ?? 'home'}:${next.machineId ?? 'points'}`,
        );
        window.requestAnimationFrame(() =>
          window.scrollTo(0, stored ? Number(stored) || 0 : 0),
        );
      } catch {
        /* Optional scroll position. */
      }
      void load();
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, [snapshot, load, changeDirty, storageNamespace, navigationAllowed]);

  useEffect(() => {
    restoredScopeKey.current = null;
    try {
      pending.current = readManagementOperation(
        window.sessionStorage,
        storageNamespace,
      );
      setRetryAvailable(pending.current !== null);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Błąd odzyskiwania operacji.',
      );
    }
  }, [storageNamespace]);

  useEffect(() => {
    if (!snapshot || snapshotScope.current !== storageNamespace) return;
    try {
      const structural = pending.current;
      const slot = readManagementSlotOperation(
        managementSessionStorage(),
        storageNamespace,
      );
      const operationId =
        structural?.body.operationId ?? slot?.body.operationId;
      if (!operationId) return;
      const key = `${storageNamespace}:${structural ? 'structure' : 'slot'}:${operationId}`;
      if (restoredScopeKey.current === key) return;
      restoredScopeKey.current = key;
      const pointId =
        structural && 'pointId' in structural ? structural.pointId : undefined;
      const machineId =
        structural && 'machineId' in structural
          ? structural.machineId
          : slot?.machineId;
      const point = snapshot.points.find(
        (row) =>
          row.id === pointId ||
          row.machines.some((item) => item.id === machineId),
      );
      if (!point) return;
      const current = locationRef.current;
      const sameMachine = current.machineId === machineId;
      const next: ManagementLocation = {
        pointId: point.id,
        machineId: machineId ?? null,
        gameId:
          structural && sameMachine ? current.gameId : (slot?.gameId ?? null),
        stake:
          structural && sameMachine ? current.stake : (slot?.stake ?? null),
      };
      if (sameManagementLocation(next, current)) return;
      if (!navigationAllowed()) return;
      locationRef.current = next;
      setLocation(next);
      window.history.replaceState(
        null,
        '',
        managementUrlWithLocation(window.location.href, next),
      );
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Błąd odzyskiwania wyboru.',
      );
    }
  }, [snapshot, storageNamespace, retryAvailable, navigationAllowed]);

  const run = async (operation: ManagementOperation) => {
    if (busyRef.current || !mounted.current || !accessRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    pending.current = operation;
    try {
      window.sessionStorage.setItem(pendingKey, JSON.stringify(operation));
      const response = (await executeManagementOperation(api, operation)) as {
        data?: unknown;
        error?: { code?: string; message?: string };
        response?: Response;
      };
      if (
        !mounted.current ||
        !accessRef.current ||
        window.sessionStorage.getItem(pendingKey) !== JSON.stringify(operation)
      )
        throw new Error(
          'Dostęp zakończony podczas zapisu. Zachowano oczekującą operację.',
        );
      if (!response.data) {
        if (
          response.response &&
          response.response.status >= 400 &&
          response.response.status < 500 &&
          ![401, 403, 429].includes(response.response.status)
        ) {
          window.sessionStorage.removeItem(pendingKey);
          pending.current = null;
          setRetryAvailable(false);
          if (operation.kind.startsWith('delete-')) {
            setDeleteTarget(null);
            setDeleteCounts(null);
            setDeleteToken('');
          }
        }
        throw new Error(
          response.error?.message ??
            'Zapis odrzucony. Odśwież dane przed ponowieniem.',
        );
      }
      window.sessionStorage.removeItem(pendingKey);
      pending.current = null;
      setRetryAvailable(false);
      setEditor(null);
      setDeleteTarget(null);
      setDeleteCounts(null);
      if (operation.kind === 'delete-point') {
        navigate(
          { pointId: null, machineId: null, gameId: null, stake: null },
          true,
        );
      } else if (operation.kind === 'delete-machine') {
        navigate(
          {
            pointId: operation.pointId,
            machineId: null,
            gameId: null,
            stake: null,
          },
          true,
        );
      }
      setNotice(
        operation.kind.startsWith('delete-')
          ? 'Usunięto wybrany zakres.'
          : 'Zapisano.',
      );
      await load();
    } catch (cause) {
      if (!mounted.current) return;
      setRetryAvailable(pending.current !== null);
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nieznany wynik zapisu. Ponów tę samą operację.',
      );
      void load(true);
    } finally {
      busyRef.current = false;
      if (mounted.current) setBusy(false);
    }
  };

  const openEditor = (next: ManagementStructureEditor) => {
    if (!mounted.current || !accessRef.current || !navigationAllowed()) return;
    if (draftDirty.current) {
      changeDirty(false);
      const cleared = { ...locationRef.current, gameId: null, stake: null };
      locationRef.current = cleared;
      setLocation(cleared);
      window.history.replaceState(
        null,
        '',
        managementUrlWithLocation(window.location.href, cleared),
      );
    }
    const nextName =
      next?.kind === 'point'
        ? (next.point?.name ?? '')
        : (next?.machine?.name ?? '');
    const nextCity = next?.kind === 'point' ? (next.point?.city ?? '') : '';
    const nextStreet = next?.kind === 'point' ? (next.point?.street ?? '') : '';
    const nextGames =
      next?.kind === 'machine'
        ? (next.machine?.assignments.map((row) => row.gameId) ?? [])
        : [];
    setEditor({
      ...next,
      baseRevision:
        next.kind === 'point'
          ? (next.point?.revision ?? 0)
          : (next.machine?.revision ?? 0),
    });
    setEditorConflict(false);
    setError('');
    setName(nextName);
    setCity(nextCity);
    setStreet(nextStreet);
    setGameIds(nextGames);
    setEditorInitial(modalSignature(nextName, nextCity, nextStreet, nextGames));
    window.requestAnimationFrame?.(() => nameInput.current?.focus());
  };
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!editor || !name.trim() || busyRef.current) return;
    const operationId = crypto.randomUUID();
    if (editor.kind === 'point') {
      const point = editor.point;
      const body = {
        operationId,
        expectedRevision: editor.baseRevision,
        name: name.trim(),
        city: city.trim(),
        street: street.trim(),
        archived: point?.archived ?? false,
      };
      await run({
        kind: 'point',
        ...(point ? { pointId: point.id } : {}),
        body,
      });
    } else {
      const { point, machine } = editor;
      const body: ManagementMachineCommand = {
        operationId,
        expectedRevision: editor.baseRevision,
        name: name.trim(),
        archived: machine?.archived ?? false,
        gameIds,
      };
      const removed =
        machine?.assignments.some((row) => !gameIds.includes(row.gameId)) ??
        false;
      if (removed && machine) {
        setConfirming(true);
        try {
          const preview = await api.previewManagementMachineUpdate(machine.id, {
            command: body,
          });
          if (!preview.data)
            throw new Error(
              (preview.error as { message?: string } | undefined)?.message ??
                'Nie udało się pobrać podglądu usuwania.',
            );
          if (
            !window.confirm(
              `Odpiąć gry i trwale usunąć ich zapisy? ${formatCounts(preview.data.counts)}`,
            )
          )
            return;
          body.previewToken = preview.data.previewToken;
        } catch (cause) {
          setError(cause instanceof Error ? cause.message : 'Błąd podglądu.');
          void load(true);
          return;
        } finally {
          setConfirming(false);
        }
      }
      await run({
        kind: 'machine',
        pointId: point.id,
        ...(machine ? { machineId: machine.id } : {}),
        body,
      });
    }
  };
  const previewDelete = async (target: ManagementStructureEditor) => {
    if (!navigationAllowed() || busyRef.current) return;
    setEditor(null);
    setConfirming(true);
    setError('');
    try {
      const revision =
        target.kind === 'point'
          ? target.point?.revision
          : target.machine?.revision;
      if (revision === undefined) return;
      const response =
        target.kind === 'point'
          ? await api.previewManagementPointDeletion(target.point!.id, {
              expectedRevision: revision,
            })
          : await api.previewManagementMachineDeletion(
              target.point.id,
              target.machine!.id,
              { expectedRevision: revision },
            );
      if (!response.data)
        throw new Error(
          (response.error as { message?: string } | undefined)?.message ??
            'Nie udało się pobrać podglądu.',
        );
      setDeleteTarget(target);
      setDeleteCounts(response.data.counts);
      setDeleteToken(response.data.previewToken);
      setDeleteRevision(revision);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Błąd podglądu.');
      void load(true);
    } finally {
      setConfirming(false);
    }
  };
  const confirmDelete = async () => {
    if (!deleteTarget || !deleteToken || !deleteCounts) return;
    const body = {
      operationId: crypto.randomUUID(),
      expectedRevision: deleteRevision,
      previewToken: deleteToken,
      confirmed: true as const,
    };
    await run(
      deleteTarget.kind === 'point'
        ? { kind: 'delete-point', pointId: deleteTarget.point!.id, body }
        : {
            kind: 'delete-machine',
            pointId: deleteTarget.point.id,
            machineId: deleteTarget.machine!.id,
            body,
          },
    );
  };
  const disabled = busy || confirming || retryAvailable || !accessAllowed;
  const selected = snapshot?.points.find(
    (point) => point.id === location.pointId,
  );
  const machine = selected?.machines.find((row) => row.id === machineId);
  const gameApi = useMemo(
    () =>
      machineId && gameClientForMachine ? gameClientForMachine(machineId) : api,
    [api, gameClientForMachine, machineId],
  );
  const assignment = machine?.assignments.find((row) => row.gameId === gameId);
  const chooseGame = (nextMachine: string, nextGame: string | null) => {
    if (nextMachine === machineId && nextGame === gameId) return;
    if (
      !navigate({
        pointId: selected?.id ?? null,
        machineId: nextMachine,
        gameId: nextGame,
        stake: null,
      })
    )
      return;
    try {
      if (nextGame)
        window.localStorage.setItem(
          `game-predictor:management:last-game:${storageNamespace}:${nextMachine}`,
          nextGame,
        );
    } catch {
      /* Optional preference. */
    }
    try {
      managementSessionStorage()?.setItem(
        `game-predictor:management:selection:${storageNamespace}`,
        JSON.stringify({ machineId: nextMachine, gameId: nextGame }),
      );
    } catch {
      /* Selection preference is optional; mutation receipts are stored separately. */
    }
  };
  const selectMachine = (
    point: ManagementPointResponse,
    next: ManagementMachineResponse,
  ) => {
    const stored = (() => {
      try {
        return window.localStorage.getItem(
          `game-predictor:management:last-game:${storageNamespace}:${next.id}`,
        );
      } catch {
        return null;
      }
    })();
    const game =
      next.assignments.find((row) => row.gameId === stored) ??
      next.assignments.find(
        (row) => row.attached && row.gameStatus === 'active',
      ) ??
      next.assignments[0];
    navigate({
      pointId: point.id,
      machineId: next.id,
      gameId: game?.gameId ?? null,
      stake: null,
    });
  };
  return (
    <section
      className="catalog-panel management-workspace"
      aria-label="Panel Administracyjny"
    >
      <div className="management-content">
        <h2>Panel Administracyjny</h2>
        <div className="management-header">
          <button
            type="button"
            onClick={() =>
              navigate({
                pointId: null,
                machineId: null,
                gameId: null,
                stake: null,
              })
            }
          >
            Punkty
          </button>
          {location.pointId ? (
            <button
              type="button"
              onClick={() =>
                navigate({
                  pointId: null,
                  machineId: null,
                  gameId: null,
                  stake: null,
                })
              }
            >
              Cofnij do punktów
            </button>
          ) : null}
          {location.machineId ? (
            <button
              type="button"
              onClick={() =>
                navigate({
                  pointId: location.pointId,
                  machineId: null,
                  gameId: null,
                  stake: null,
                })
              }
            >
              Cofnij do maszyn
            </button>
          ) : null}
          {headerActions}
        </div>
        <div className="management-actions">
          <button onClick={() => void load()} disabled={busy || !accessAllowed}>
            Odśwież
          </button>
          {!location.pointId ? (
            <button
              onClick={() => openEditor({ kind: 'point' })}
              disabled={disabled}
            >
              Dodaj punkt
            </button>
          ) : null}
        </div>
        {loading ? <p role="status">Ładowanie punktów…</p> : null}
        {error ? <p role="alert">{error}</p> : null}
        {retryAvailable ? (
          <button
            disabled={busy || !accessAllowed}
            onClick={() => {
              if (pending.current) void run(pending.current);
            }}
          >
            Ponów ten sam zapis
          </button>
        ) : null}
        {notice ? <p role="status">{notice}</p> : null}
        {snapshot && !location.pointId && !snapshot.points.length ? (
          <p>Brak punktów. Dodaj pierwszy punkt.</p>
        ) : null}
        {!location.pointId ? (
          <div className="management-tiles">
            {snapshot?.points
              .filter((point) => !point.archived)
              .map((point) => (
                <article className="management-tile" key={point.id}>
                  <button
                    className="management-tile-choice"
                    onClick={() =>
                      navigate({
                        pointId: point.id,
                        machineId: null,
                        gameId: null,
                        stake: null,
                      })
                    }
                  >
                    <strong>{point.name}</strong>
                    <span>
                      {point.city}, {point.street}
                    </span>
                    <span>{point.machines.length} maszyn</span>
                  </button>
                  <div className="management-tile-controls">
                    <button
                      aria-label={`Edytuj punkt ${point.name}`}
                      title="Edytuj"
                      disabled={disabled}
                      onClick={() => openEditor({ kind: 'point', point })}
                    >
                      ✎
                    </button>
                    <button
                      aria-label={`Usuń punkt ${point.name}`}
                      title="Usuń"
                      disabled={disabled}
                      onClick={() =>
                        void previewDelete({ kind: 'point', point })
                      }
                    >
                      🗑
                    </button>
                  </div>
                </article>
              ))}
          </div>
        ) : null}
        {!location.pointId &&
        snapshot?.points.some((point) => point.archived) ? (
          <details className="management-legacy">
            <summary>Archiwalne punkty</summary>
            <div className="management-tiles">
              {snapshot.points
                .filter((point) => point.archived)
                .map((point) => (
                  <article className="management-tile" key={point.id}>
                    <strong>{point.name}</strong>
                    <button
                      disabled={disabled}
                      onClick={() =>
                        void previewDelete({ kind: 'point', point })
                      }
                    >
                      Usuń punkt
                    </button>
                  </article>
                ))}
            </div>
          </details>
        ) : null}
        {selected && !machine ? (
          <section aria-label={`Maszyny: ${selected.name}`}>
            <h3>{selected.name} — maszyny</h3>
            {!selected.archived ? (
              <button
                disabled={disabled}
                onClick={() => openEditor({ kind: 'machine', point: selected })}
              >
                Dodaj maszynę
              </button>
            ) : null}
            {!selected.machines.length ? <p>Brak maszyn.</p> : null}
            <div className="management-tiles">
              {selected.machines
                .filter((machine) => !machine.archived)
                .map((machine) => (
                  <article className="management-tile" key={machine.id}>
                    <button
                      className="management-tile-choice"
                      onClick={() => selectMachine(selected, machine)}
                    >
                      <strong>{machine.name}</strong>
                      <span>{machine.assignments.length} gier</span>
                    </button>
                    <div className="management-tile-controls">
                      <button
                        disabled={disabled || selected.archived}
                        aria-label={`Edytuj maszynę ${machine.name}`}
                        title="Edytuj"
                        onClick={() =>
                          openEditor({
                            kind: 'machine',
                            point: selected,
                            machine,
                          })
                        }
                      >
                        ✎
                      </button>
                      <button
                        disabled={disabled}
                        aria-label={`Usuń maszynę ${machine.name}`}
                        title="Usuń"
                        onClick={() =>
                          void previewDelete({
                            kind: 'machine',
                            point: selected,
                            machine,
                          })
                        }
                      >
                        🗑
                      </button>
                    </div>
                  </article>
                ))}
            </div>
            {selected.machines.some((item) => item.archived) ? (
              <details className="management-legacy">
                <summary>Archiwalne maszyny</summary>
                <div className="management-tiles">
                  {selected.machines
                    .filter((item) => item.archived)
                    .map((item) => (
                      <article className="management-tile" key={item.id}>
                        <strong>{item.name}</strong>
                        <button
                          disabled={disabled}
                          onClick={() =>
                            void previewDelete({
                              kind: 'machine',
                              point: selected,
                              machine: item,
                            })
                          }
                        >
                          Usuń maszynę
                        </button>
                      </article>
                    ))}
                </div>
              </details>
            ) : null}
          </section>
        ) : null}
        {machine ? (
          <section aria-label={`Gry maszyny: ${machine.name}`}>
            <h3>{machine.name} — gry i zapisane stawki</h3>
            <button
              disabled={disabled || selected?.archived || machine.archived}
              onClick={() =>
                selected &&
                openEditor({ kind: 'machine', point: selected, machine })
              }
            >
              Edytuj maszynę i gry
            </button>
            <label>
              Gra
              <select
                aria-label="Gra maszyny"
                disabled={!accessAllowed}
                value={gameId ?? ''}
                onChange={(event) =>
                  chooseGame(machine.id, event.target.value || null)
                }
              >
                <option value="" disabled>
                  Wybierz grę
                </option>
                {machine.assignments.map((row) => (
                  <option key={row.gameId} value={row.gameId}>
                    {row.gameName}
                    {!row.attached
                      ? ' · Odłączona'
                      : row.gameStatus !== 'active'
                        ? ' · Archiwalna'
                        : ''}
                  </option>
                ))}
              </select>
            </label>
            {!machine.assignments.length ? (
              <p>Przypisz grę do maszyny, aby zapisać układ.</p>
            ) : null}
            {assignment && selected && managementSlotsAvailable(gameApi) ? (
              <ManagementGameWorkspace
                key={`${storageNamespace}:${machine.id}:${assignment.gameId}`}
                api={gameApi as ManagementGameClient}
                machineId={machine.id}
                gameId={assignment.gameId}
                accessAllowed={accessAllowed}
                writeAllowed={managementSlotWritesAllowed(
                  selected.archived,
                  machine.archived,
                  assignment,
                )}
                storageNamespace={storageNamespace}
                onDirtyChange={changeDirty}
                pauseRefresh={deleteTarget !== null || confirming}
                selectedStake={location.stake}
                onStakeSelected={(stake) => {
                  if (locationRef.current.stake === stake) return;
                  const next = { ...locationRef.current, stake };
                  locationRef.current = next;
                  setLocation(next);
                  window.history.pushState(
                    null,
                    '',
                    managementUrlWithLocation(window.location.href, next),
                  );
                }}
              />
            ) : null}
          </section>
        ) : null}
      </div>
      {editor ? (
        <ManagementStructureModal
          editor={editor}
          activeGames={snapshot?.activeGames ?? []}
          name={name}
          city={city}
          street={street}
          gameIds={gameIds}
          disabled={disabled}
          conflict={editorConflict}
          nameInput={nameInput}
          setName={setName}
          setCity={setCity}
          setStreet={setStreet}
          setGameIds={setGameIds}
          onSave={save}
          onClose={() => {
            if (navigationAllowed()) setEditor(null);
          }}
        />
      ) : null}
      {deleteTarget && deleteCounts ? (
        <div
          className="management-modal"
          role="dialog"
          aria-modal="true"
          aria-label="Potwierdzenie usunięcia"
        >
          <h3>
            Trwale usunąć {deleteTarget.kind === 'point' ? 'punkt' : 'maszynę'}?
          </h3>
          <p>{formatCounts(deleteCounts)}</p>
          <p>Zapisy, konteksty i dziennik tego zakresu zostaną usunięte.</p>
          <div className="management-actions">
            <button disabled={disabled} onClick={() => void confirmDelete()}>
              Potwierdź usunięcie
            </button>
            <button
              disabled={busy}
              onClick={() => {
                setDeleteTarget(null);
                setDeleteCounts(null);
                setDeleteToken('');
              }}
            >
              Anuluj
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function formatCounts(counts: ManagementMutationCounts): string {
  return `Punkty: ${counts.points ?? 0}, maszyny: ${counts.machines ?? 0}, przypisania: ${counts.assignments ?? 0}, zapisy: ${counts.slots ?? 0}, konteksty: ${counts.searchContexts ?? 0}, wpisy dziennika: ${counts.journalEntries ?? 0}.`;
}

function modalSignature(
  name: string,
  city: string,
  street: string,
  gameIds: readonly string[],
): string {
  return JSON.stringify([name, city, street, [...gameIds].sort()]);
}
