'use client';

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type SetStateAction,
} from 'react';
import type {
  BoardSearchPattern,
  BoardSearchResponse,
  BoardSearchSequenceResponse,
} from '@game-predictor/admin-api-client';
import type { BoardSearchDataSource } from './board-search-data-source';
import { apiErrorMessage } from './api-error';
import {
  createBoardSearchEditorState,
  type BoardSearchEditorState,
  type BoardSearchEntryOrder,
} from './board-search-editor-state';
import {
  createBoardSearchResultsState,
  type BoardSearchResultsState,
} from './board-search-results-state';
import {
  boardSearchSequenceEditor,
  boardSearchSequenceEditorsFromPatterns,
  boardSearchSequenceInput,
  boardSearchSequenceKey,
  boardSearchSequenceStorageKey,
  readBoardSearchSequenceLocalState,
  type BoardSearchSequenceLocalState,
  type BoardSearchSubmittedSequence,
} from './board-search-sequence-state';

const STORAGE_FAILURE =
  'Nie udało się zachować wyszukiwania w przeglądarce. Możesz pracować dalej; poprzedni zestaw może wrócić po odświeżeniu.';
type Status =
  | { readonly kind: 'idle' | 'loading' }
  | { readonly kind: 'error'; readonly message: string }
  | { readonly kind: 'ready'; readonly result: BoardSearchResponse };
export type SequenceSearchOptions = {
  readonly patterns?: BoardSearchPattern[];
  readonly limit?: number;
  readonly scope?: BoardSearchSubmittedSequence['scope'];
  readonly preserveSelection?: boolean;
  readonly selectedStart?: number | null;
  readonly onResults?: (state: BoardSearchResultsState) => void;
};

/** Independent editor, submitted snapshot and visible response; nothing secret is persisted. */
export function useBoardSearchSequence({
  enabled,
  api,
  gameId,
  scope,
  ready,
  activeCodes,
  hasReplay,
}: {
  readonly enabled: boolean;
  readonly api: BoardSearchDataSource;
  readonly gameId: string;
  readonly scope: string;
  readonly ready: boolean;
  readonly activeCodes: ReadonlySet<string>;
  readonly hasReplay: boolean;
}) {
  const [editors, setEditors] = useState<BoardSearchEditorState[]>([
    createBoardSearchEditorState(),
  ]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [entryOrder, setEntryOrder] =
    useState<BoardSearchEntryOrder>('columns');
  const [limit, setLimit] = useState(15);
  const [lastSubmitted, setLastSubmitted] =
    useState<BoardSearchSubmittedSequence | null>(null);
  const [visibleSubmitted, setVisibleSubmitted] =
    useState<BoardSearchSubmittedSequence | null>(null);
  const [successfulKey, setSuccessfulKey] = useState<string | null>(null);
  const [selectedStart, setSelectedStart] = useState<number | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const [response, setResponse] = useState<BoardSearchResponse | null>(null);
  const [sequenceResponse, setSequenceResponse] =
    useState<BoardSearchSequenceResponse | null>(null);
  const [results, setResults] = useState<BoardSearchResultsState | null>(null);
  const resultStarts = useRef<readonly number[]>([]);
  const [contextId, setContextId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [storageNotice, setStorageNotice] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const hydratedRef = useRef(false);
  const pendingRestore = useRef<{
    query: BoardSearchSubmittedSequence;
    selected: number | null;
  } | null>(null);
  const epoch = useRef(0);
  const requestId = useRef(0);
  const loading = useRef(false);
  const mounted = useRef(true);
  const [calculationBusy, setCalculationBusy] = useState(false);
  const [resultRevision, setResultRevision] = useState(0);
  const [repeatPending, setRepeatPending] =
    useState<SequenceSearchOptions | null>(null);
  const calculationBusyRef = useRef(false);
  const storageKey = boardSearchSequenceStorageKey(scope);
  const input = useMemo(
    () => boardSearchSequenceInput(editors, activeCodes),
    [editors, activeCodes],
  );
  const inputKey = boardSearchSequenceKey(input.patterns);
  const visibleKey =
    visibleSubmitted === null
      ? ''
      : boardSearchSequenceKey(visibleSubmitted.patterns);
  const draftChanged = input.error !== null || inputKey !== visibleKey;
  const activeSequence =
    sequenceResponse?.results[results?.activeIndex ?? 0] ?? null;

  useEffect(() => {
    mounted.current = true;
    const invalidate = () => {
      requestId.current++;
      epoch.current++;
    };
    return () => {
      mounted.current = false;
      invalidate();
    };
  }, []);

  const onBusyChange = (busy: boolean) => {
    calculationBusyRef.current = busy;
    if (mounted.current) setCalculationBusy(busy);
  };

  function setEditor(action: SetStateAction<BoardSearchEditorState>) {
    setEditors((previous) =>
      previous.map((editor, index) =>
        index !== activeIndex
          ? editor
          : typeof action === 'function'
            ? action(editor)
            : action,
      ),
    );
  }

  function selectResults(state: BoardSearchResultsState | null) {
    setResults(state);
    const index = state?.activeIndex ?? 0;
    setSelectedStart(
      resultStarts.current[index] ??
        state?.results[index]?.sequenceNumber ??
        null,
    );
  }

  function fail(error: unknown) {
    const code =
      error !== null && typeof error === 'object' && 'code' in error
        ? String(error.code)
        : '';
    if (
      /UNAUTHORIZED|EXPIRED|REVOKED|ACCESS_DENIED|BOARD_SEARCH_SHARE_(TOKEN_INVALID|NOT_FOUND|DISABLED|LOCKED)/.test(
        code,
      )
    ) {
      setResponse(null);
      setResults(null);
      setSequenceResponse(null);
      setContextId(null);
      setSelectedStart(null);
      resultStarts.current = [];
    }
    setStatus({
      kind: 'error',
      message: /RATE_LIMIT|BUSY|CALCULATION_IN_PROGRESS/.test(code)
        ? 'Trwa inne obliczenie lub przekroczono limit. Spróbuj ponownie za chwilę.'
        : apiErrorMessage(
            error,
            'Nie udało się wyszukać plansz. Spróbuj ponownie.',
          ),
    });
  }

  function search(options: SequenceSearchOptions = {}) {
    if (!enabled || loading.current || calculationBusyRef.current) return;
    const patterns = options.patterns ?? input.patterns;
    const validation = boardSearchSequenceInput(
      boardSearchSequenceEditorsFromPatterns(patterns),
      activeCodes,
    );
    if (
      (options.patterns === undefined && input.error !== null) ||
      validation.error !== null
    ) {
      setNotice(
        options.patterns === undefined
          ? (input.error ?? validation.error)
          : validation.error,
      );
      return;
    }
    const submitted: BoardSearchSubmittedSequence = {
      patterns,
      limit: options.limit ?? limit,
      scope: options.scope ?? 'all_searchable',
    };
    const keepStart =
      options.selectedStart !== undefined
        ? options.selectedStart
        : options.preserveSelection ||
            (boardSearchSequenceKey(patterns) === visibleKey &&
              submitted.scope === visibleSubmitted?.scope)
          ? selectedStart
          : null;
    const id = ++requestId.current;
    setRepeatPending(null);
    loading.current = true;
    setStatus({ kind: 'loading' });
    setNotice(null);
    setLastSubmitted(submitted);
    const request =
      patterns.length === 1
        ? api.searchGameBoards(gameId, {
            cells: patterns[0].cells,
            scope: submitted.scope,
            limit: submitted.limit,
          })
        : api.searchGameBoardSequence!(gameId, submitted);
    void request
      .then((answer) => {
        if (!mounted.current || id !== requestId.current) return;
        if (answer.error !== undefined || answer.data === undefined) {
          fail(answer.error);
          return;
        }
        const multi = 'patternCount' in answer.data ? answer.data : null;
        const data: BoardSearchResponse =
          multi === null
            ? (answer.data as BoardSearchResponse)
            : {
                gameId: multi.gameId,
                scope: multi.scope,
                queryCellCount: multi.queryCellCount,
                superGameState: multi.superGameState,
                results: multi.results.map(
                  (result) => result.boards[result.boards.length - 1],
                ),
              };
        let fresh = createBoardSearchResultsState(data.results);
        if (keepStart !== null) {
          const index =
            multi === null
              ? data.results.findIndex(
                  (board) => board.sequenceNumber === keepStart,
                )
              : multi.results.findIndex(
                  (result) => result.startSequenceNumber === keepStart,
                );
          if (index >= 0) fresh = { ...fresh, activeIndex: index };
          else if (data.results.length > 0)
            setNotice(
              'Poprzedniego dopasowania nie ma już w wynikach. Wybrano pierwsze.',
            );
        }
        setResponse(data);
        setSequenceResponse(multi);
        resultStarts.current =
          multi?.results.map((result) => result.startSequenceNumber) ??
          data.results.map((board) => board.sequenceNumber);
        setResults(fresh);
        setSelectedStart(
          multi?.results[fresh.activeIndex]?.startSequenceNumber ??
            fresh.results[fresh.activeIndex]?.sequenceNumber ??
            null,
        );
        setContextId(answer.searchContextId ?? null);
        setResultRevision((revision) => revision + 1);
        setVisibleSubmitted(submitted);
        setSuccessfulKey(boardSearchSequenceKey(patterns));
        setStatus({ kind: 'ready', result: data });
        options.onResults?.(fresh);
      })
      .catch((error: unknown) => {
        if (mounted.current && id === requestId.current) fail(error);
      })
      .finally(() => {
        if (id === requestId.current) loading.current = false;
      });
  }

  // Replay has priority even while a calculator delays a queued restore.
  useEffect(() => {
    if (hasReplay) pendingRestore.current = null;
  }, [hasReplay]);
  useEffect(() => {
    if (!enabled || !ready || hydratedRef.current) return;
    const revision = epoch.current;
    queueMicrotask(() => {
      if (!mounted.current || revision !== epoch.current || hydratedRef.current)
        return;
      hydratedRef.current = true;
      if (!hasReplay) {
        try {
          const raw = window.localStorage.getItem(storageKey);
          if (raw !== null) {
            const saved = readBoardSearchSequenceLocalState(raw, scope);
            setEditors(saved.patterns.map(boardSearchSequenceEditor));
            setActiveIndex(saved.activeIndex);
            setEntryOrder(saved.entryOrder);
            setLastSubmitted(saved.lastSubmitted);
            setSelectedStart(saved.selectedStartSequenceNumber);
            if (saved.lastSubmitted !== null) {
              setLimit(saved.lastSubmitted.limit);
              pendingRestore.current = {
                query: saved.lastSubmitted,
                selected: saved.selectedStartSequenceNumber,
              };
            }
          }
        } catch (error) {
          setStorageNotice(
            error instanceof SyntaxError ||
              (error instanceof Error &&
                error.message === 'Nieprawidłowy zapis wyszukiwania.')
              ? 'Zapis wyszukiwania jest nieprawidłowy lub ma inną wersję. Rozpoczęto pusty zestaw.'
              : STORAGE_FAILURE,
          );
        }
      }
      setHydrated(true);
    });
  }, [enabled, ready, hasReplay, storageKey, scope]);

  useEffect(() => {
    if (
      !enabled ||
      !hydrated ||
      !ready ||
      hasReplay ||
      calculationBusy ||
      pendingRestore.current === null
    )
      return;
    const restore = pendingRestore.current;
    pendingRestore.current = null;
    const revision = epoch.current;
    queueMicrotask(() => {
      if (mounted.current && revision === epoch.current)
        search({ ...restore.query, selectedStart: restore.selected });
    });
    // Search is an event over the hydrated state, not an effect dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, hydrated, ready, hasReplay, calculationBusy]);

  useEffect(() => {
    if (!enabled || !hydrated) return;
    const saved: BoardSearchSequenceLocalState = {
      version: 1,
      scope,
      patterns: editors.map((editor) => editor.cells),
      activeIndex,
      entryOrder,
      lastSubmitted,
      selectedStartSequenceNumber:
        visibleSubmitted !== null &&
        lastSubmitted !== null &&
        (boardSearchSequenceKey(lastSubmitted.patterns) !==
          boardSearchSequenceKey(visibleSubmitted.patterns) ||
          lastSubmitted.scope !== visibleSubmitted.scope)
          ? null
          : selectedStart,
    };
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(saved));
    } catch {
      queueMicrotask(() => {
        if (mounted.current) setStorageNotice(STORAGE_FAILURE);
      });
    }
  }, [
    enabled,
    hydrated,
    scope,
    storageKey,
    editors,
    activeIndex,
    entryOrder,
    lastSubmitted,
    visibleSubmitted,
    selectedStart,
  ]);

  function replaceDraft(patterns: BoardSearchPattern[], nextLimit: number) {
    setRepeatPending(null);
    pendingRestore.current = null;
    epoch.current++;
    const next = boardSearchSequenceEditorsFromPatterns(patterns);
    setEditors(next);
    setActiveIndex(next.length - 1);
    setLimit(nextLimit);
    // A replay supersedes an in-flight search, retaining the server slot guard.
    requestId.current++;
    loading.current = false;
  }

  function clear() {
    resultStarts.current = [];
    setRepeatPending(null);
    epoch.current++;
    requestId.current++;
    loading.current = false;
    pendingRestore.current = null;
    const empty = createBoardSearchEditorState();
    setEditors([empty]);
    setActiveIndex(0);
    setLastSubmitted(null);
    setVisibleSubmitted(null);
    setSuccessfulKey(null);
    setResponse(null);
    setSequenceResponse(null);
    setResults(null);
    setContextId(null);
    setSelectedStart(null);
    setNotice(null);
    setStatus({ kind: 'idle' });
    // Immediate durable clear: a navigation before the next effect must not restore the old set.
    try {
      window.localStorage.setItem(
        storageKey,
        JSON.stringify({
          version: 1,
          scope,
          patterns: [empty.cells],
          activeIndex: 0,
          entryOrder,
          lastSubmitted: null,
          selectedStartSequenceNumber: null,
        }),
      );
    } catch {
      setStorageNotice(STORAGE_FAILURE);
    }
  }

  const canNext =
    activeIndex === editors.length - 1 &&
    editors.length < 4 &&
    input.error === null &&
    input.patterns.length === editors.length &&
    successfulKey === inputKey &&
    visibleSubmitted?.limit === limit &&
    status.kind === 'ready';
  useEffect(() => {
    if (
      repeatPending === null ||
      calculationBusy ||
      status.kind === 'loading' ||
      visibleSubmitted === null
    )
      return;
    const revision = epoch.current;
    queueMicrotask(() => {
      if (!mounted.current || revision !== epoch.current) return;
      setRepeatPending(null);
      search(repeatPending);
    });
    // The request is a one-shot refresh after an edit; waiting for a real
    // calculation to settle must not silently drop it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repeatPending, calculationBusy, status.kind]);
  return {
    editor: editors[activeIndex],
    editors,
    setEditor,
    activeIndex,
    setActiveIndex,
    entryOrder,
    setEntryOrder,
    limit,
    setLimit,
    status,
    response,
    results,
    setResults: selectResults,
    activeSequence,
    contextId,
    notice,
    storageNotice,
    hydrated,
    calculationBusy,
    resultRevision,
    onBusyChange,
    inputError: input.error,
    draftChanged,
    stale:
      response !== null &&
      (draftChanged ||
        visibleSubmitted?.limit !== limit ||
        status.kind === 'loading' ||
        status.kind === 'error'),
    searchKey: `${visibleKey}:${visibleSubmitted?.scope ?? ''}`,
    lastSubmitted,
    canNext,
    next: () => {
      if (canNext) {
        setEditors((previous) => [...previous, createBoardSearchEditorState()]);
        setActiveIndex(editors.length);
      }
    },
    search,
    repeat: () => {
      if (visibleSubmitted !== null)
        setRepeatPending({
          ...visibleSubmitted,
          limit,
          preserveSelection: true,
        });
    },
    repeatWithLimit: (nextLimit: number) => {
      if (visibleSubmitted !== null && !loading.current)
        setRepeatPending({
          ...visibleSubmitted,
          limit: nextLimit,
          preserveSelection: true,
        });
    },
    replaceDraft,
    clear,
  };
}
