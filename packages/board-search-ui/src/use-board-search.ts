'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import type { BoardSearchResponse } from '@game-predictor/admin-api-client';
import type { BoardSearchDataSource } from './board-search-data-source';
import { apiErrorMessage } from './api-error';
import {
  createBoardSearchEditorState,
  type BoardSearchEditorState,
  type BoardSearchEntryOrder,
} from './board-search-editor-state';
import {
  BOARD_SEARCH_LIMIT_DEFAULT,
  createBoardSearchResultsState,
  type BoardSearchResultsState,
} from './board-search-results-state';
import {
  type BoardSearchPattern,
  boardSearchStorageKey,
  readBoardSearchLocalState,
  writeBoardSearchLocalState,
  boardSearchSequenceEditor,
  boardSearchSequenceEditorsFromPatterns,
  boardSearchSequenceInput,
  boardSearchSequenceKey,
  boardSearchSequenceStorageKey,
  readBoardSearchSequenceLocalState,
  type BoardSearchSequenceLocalState,
  type BoardSearchSubmittedSequence,
} from './board-search-local-state';

const STORAGE_FAILURE =
  'Nie udało się zachować wyszukiwania w przeglądarce. Możesz pracować dalej; poprzedni zestaw może wrócić po odświeżeniu.';
type Status =
  | { readonly kind: 'idle' | 'loading' }
  | { readonly kind: 'error'; readonly message: string }
  | { readonly kind: 'ready'; readonly result: BoardSearchResponse };
export type SingleSearchOptions = {
  readonly patterns?: BoardSearchPattern[];
  readonly limit?: number;
  readonly scope?: BoardSearchSubmittedSequence['scope'];
  readonly preserveSelection?: boolean;
  readonly selectedStart?: number | null;
  readonly onResults?: (state: BoardSearchResultsState) => void;
};

/** Independent editor, submitted snapshot and visible response; nothing secret is persisted. */
export function useBoardSearch({
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
  const [editor, setEditor] = useState<BoardSearchEditorState>(
    createBoardSearchEditorState,
  );
  const [entryOrder, setEntryOrder] =
    useState<BoardSearchEntryOrder>('columns');
  const [limit, setLimit] = useState(BOARD_SEARCH_LIMIT_DEFAULT);
  const [lastSubmitted, setLastSubmitted] =
    useState<BoardSearchSubmittedSequence | null>(null);
  const [visibleSubmitted, setVisibleSubmitted] =
    useState<BoardSearchSubmittedSequence | null>(null);
  const [selectedStart, setSelectedStart] = useState<number | null>(null);
  const [status, setStatus] = useState<Status>({ kind: 'idle' });
  const [response, setResponse] = useState<BoardSearchResponse | null>(null);
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
  const [repeatPending, setRepeatPending] = useState<{
    reason: 'limit' | 'correction';
    options: SingleSearchOptions;
  } | null>(null);
  const calculationBusyRef = useRef(false);
  const storageKey = boardSearchStorageKey(scope);
  const input = useMemo(
    () => boardSearchSequenceInput([editor], activeCodes),
    [editor, activeCodes],
  );
  const inputKey = boardSearchSequenceKey(input.patterns);
  const visibleKey =
    visibleSubmitted === null
      ? ''
      : boardSearchSequenceKey(visibleSubmitted.patterns);
  const draftChanged = input.error !== null || inputKey !== visibleKey;
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

  function search(options: SingleSearchOptions = {}) {
    if (!enabled || loading.current || calculationBusyRef.current) return;
    const patterns = (options.patterns ?? input.patterns).map((pattern) => ({
      cells: [...pattern.cells].sort(
        (left, right) => left.cellIndex - right.cellIndex,
      ),
    }));
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
    const request = api.searchGameBoards(gameId, {
      cells: patterns[0].cells,
      scope: submitted.scope,
      limit: submitted.limit,
    });
    void request
      .then((answer) => {
        if (!mounted.current || id !== requestId.current) return;
        if (answer.error !== undefined || answer.data === undefined) {
          fail(answer.error);
          return;
        }
        const data = answer.data;
        let fresh = createBoardSearchResultsState(data.results);
        if (keepStart !== null) {
          const index = data.results.findIndex(
            (board) => board.sequenceNumber === keepStart,
          );
          if (index >= 0) fresh = { ...fresh, activeIndex: index };
          else if (data.results.length > 0)
            setNotice(
              'Poprzedniego dopasowania nie ma już w wynikach. Wybrano pierwsze.',
            );
        }
        setResponse(data);
        resultStarts.current = data.results.map(
          (board) => board.sequenceNumber,
        );
        setResults(fresh);
        setSelectedStart(
          fresh.results[fresh.activeIndex]?.sequenceNumber ?? null,
        );
        setContextId(answer.searchContextId ?? null);
        setResultRevision((revision) => revision + 1);
        setVisibleSubmitted(submitted);
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
          const current = window.localStorage.getItem(storageKey);
          const raw =
            current ??
            window.localStorage.getItem(boardSearchSequenceStorageKey(scope));
          if (raw !== null) {
            const saved =
              current === null
                ? readBoardSearchSequenceLocalState(raw, scope)
                : readBoardSearchLocalState(raw, scope);
            setEditor(boardSearchSequenceEditor(saved.patterns[0]));
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
              : error instanceof Error &&
                  error.message.includes('zostało usunięte')
                ? error.message
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
      patterns: [editor.cells],
      activeIndex: 0,
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
      window.localStorage.setItem(
        storageKey,
        writeBoardSearchLocalState(saved),
      );
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
    editor,
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
    if (next.length !== 1) {
      setNotice(
        'Wyszukiwanie wielu układów zostało usunięte. Wpisz jedną planszę.',
      );
      return;
    }
    setEditor(next[0]);
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
    setEditor(empty);
    setLastSubmitted(null);
    setVisibleSubmitted(null);
    setResponse(null);
    setResults(null);
    setContextId(null);
    setSelectedStart(null);
    setNotice(null);
    setStatus({ kind: 'idle' });
    // Immediate durable clear: a navigation before the next effect must not restore the old set.
    try {
      window.localStorage.setItem(
        storageKey,
        writeBoardSearchLocalState({
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

  useEffect(() => {
    if (repeatPending === null) return;
    let cancelled = false;
    // Limit refreshes belong to the unchanged draft. Corrections belong to
    // the visible results and must still refresh them after draft edits.
    if (repeatPending.reason === 'limit' && draftChanged) {
      queueMicrotask(() => {
        if (!cancelled && mounted.current)
          setRepeatPending((pending) =>
            pending === repeatPending ? null : pending,
          );
      });
      return () => {
        cancelled = true;
      };
    }
    if (
      calculationBusy ||
      status.kind === 'loading' ||
      visibleSubmitted === null
    )
      return;
    const revision = epoch.current;
    queueMicrotask(() => {
      if (cancelled || !mounted.current || revision !== epoch.current) return;
      setRepeatPending(null);
      search(repeatPending.options);
    });
    return () => {
      cancelled = true;
    };
    // Corrections are one-shot refreshes of the visible snapshot, while a
    // limit refresh becomes obsolete as soon as the draft changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repeatPending, calculationBusy, status.kind, draftChanged]);
  return {
    editor,
    setEditor,
    entryOrder,
    setEntryOrder,
    limit,
    setLimit,
    status,
    response,
    results,
    setResults: selectResults,
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
    search,
    repeat: () => {
      if (visibleSubmitted !== null)
        setRepeatPending({
          reason: 'correction',
          options: { ...visibleSubmitted, limit, preserveSelection: true },
        });
    },
    repeatWithLimit: (nextLimit: number) => {
      if (visibleSubmitted !== null && !loading.current)
        setRepeatPending((pending) => ({
          // A new limit may update a correction refresh, never downgrade it.
          reason: pending?.reason === 'correction' ? 'correction' : 'limit',
          options: {
            ...(pending?.reason === 'correction'
              ? pending.options
              : visibleSubmitted),
            limit: nextLimit,
            preserveSelection: true,
          },
        }));
    },
    replaceDraft,
    clear,
  };
}
