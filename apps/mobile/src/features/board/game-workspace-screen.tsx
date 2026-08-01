import {
  TARGET_SCAN_LIMIT_DEFAULT,
  type ForecastPeak,
} from '@game-predictor/shared-ts';
import { useCallback, useReducer, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  type LayoutChangeEvent,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type { LocalGameConfig } from '@/data/local-layout-repository';
import {
  TargetPeakRow,
  targetPeakKey,
} from '@/features/target/target-peak-row';
import {
  TargetResultsEmpty,
  TargetResultsHeader,
} from '@/features/target/target-results-header';
import {
  parseTargetScanLimit,
  TargetScanLimitInput,
} from '@/features/target/target-scan-limit-input';
import {
  useTargetForecast,
  type TargetForecastRepository,
} from '@/features/target/use-target-forecast';

import { BoardGrid } from './board-grid';
import {
  boardReducer,
  canUndo,
  createBoardState,
  createEmptyBoardState,
  enteredCellCount,
  isBoardFull,
  type BoardState,
} from './board-reducer';
import { boardColors } from './board-theme';
import { CandidateLayoutModal } from './candidate-layout-modal';
import { GameHeader } from './game-header';
import { ResultSummaryCard } from './result-summary-card';
import { SymbolSelection } from './symbol-selection';
import {
  useExactMatching,
  type ExactMatchRepository,
} from './use-exact-matching';
import {
  useNextLayoutNavigation,
  type NextLayoutRepository,
} from './use-next-layout-navigation';
import {
  usePrefixMatching,
  type PrefixMatchRepository,
  type PrefixMatchingState,
} from './use-prefix-matching';

export type MatchingRepository = ExactMatchRepository &
  NextLayoutRepository &
  PrefixMatchRepository &
  TargetForecastRepository;

const EMPTY_TARGET_PEAKS: readonly ForecastPeak[] = Object.freeze([]);

function ResultsListFooter() {
  return <View style={styles.listFooter} />;
}

type Props = {
  diagnostics: SnapshotDiagnostics;
  games: readonly LocalGameConfig[];
  repository: MatchingRepository;
};

function initialState(games: readonly LocalGameConfig[]): BoardState {
  const firstGame = games[0];
  return firstGame === undefined
    ? createEmptyBoardState()
    : createBoardState(firstGame.id, firstGame.rows, firstGame.columns);
}

type PrefixStatusProps = {
  state: PrefixMatchingState;
};

function PrefixStatus({ state }: PrefixStatusProps) {
  if (state.status === 'error') {
    return (
      <View
        accessibilityLiveRegion="assertive"
        style={[styles.matchCard, styles.matchErrorCard]}
        testID="prefix-error"
      >
        <Text style={styles.matchErrorCode}>{state.error.code}</Text>
        <Text style={styles.matchErrorText}>{state.error.message}</Text>
      </View>
    );
  }
  if (state.status === 'loading') {
    return (
      <View
        accessibilityLiveRegion="polite"
        style={styles.matchCard}
        testID="prefix-loading"
      >
        <ActivityIndicator color={boardColors.primary} size="small" />
        <Text style={styles.matchLoadingText}>Sprawdzanie prefiksu…</Text>
      </View>
    );
  }
  if (state.status === 'ready') {
    return (
      <View
        accessibilityLiveRegion="polite"
        style={styles.matchCard}
        testID="prefix-ready"
      >
        <Text style={styles.matchReadyTitle}>Kandydaci lokalni</Text>
        <Text style={styles.matchCount}>{state.candidateCount}</Text>
      </View>
    );
  }
  return (
    <View style={styles.matchCard} testID="prefix-idle">
      <Text style={styles.matchReadyTitle}>Kandydaci lokalni</Text>
      <Text style={styles.matchIdleText}>
        Wprowadź pierwszy symbol, aby rozpocząć wyszukiwanie.
      </Text>
    </View>
  );
}

export function GameWorkspaceScreen({ diagnostics, games, repository }: Props) {
  const targetResultsListRef = useRef<FlatList<ForecastPeak>>(null);
  const latestScrollOffsetRef = useRef(0);
  const [state, dispatch] = useReducer(boardReducer, games, initialState);
  const [targetScanLimitDraft, setTargetScanLimitDraft] = useState(
    String(TARGET_SCAN_LIMIT_DEFAULT),
  );
  const [targetResultsStartY, setTargetResultsStartY] = useState<number | null>(
    null,
  );
  const [showScrollToTop, setShowScrollToTop] = useState(false);
  const targetScanLimit = parseTargetScanLimit(targetScanLimitDraft);
  const selectedGame =
    games.find((game) => game.id === state.selectedGameId) ?? null;
  const enteredCount = enteredCellCount(state);
  const boardFull = isBoardFull(state);
  const prefixMatching = usePrefixMatching(
    repository,
    selectedGame,
    state.cells,
    state.rejectedSuggestionPrefix,
    !boardFull,
  );
  const exactMatching = useExactMatching(
    repository,
    selectedGame,
    state.cells,
    state.anchorSequenceNumber,
  );
  const uniqueSequenceNumber =
    exactMatching.status === 'ready' &&
    exactMatching.result?.status === 'unique'
      ? exactMatching.result.candidate.sequenceNumber
      : null;
  const targetForecast = useTargetForecast(
    repository,
    selectedGame,
    uniqueSequenceNumber,
    targetScanLimit,
    diagnostics,
  );
  const handleLoadNextLayout = useCallback(
    (candidate: {
      readonly cells: readonly number[];
      readonly sequenceNumber: number;
    }) => {
      dispatch({
        cells: candidate.cells,
        sequenceNumber: candidate.sequenceNumber,
        type: 'load_anchored_layout',
      });
    },
    [],
  );
  const nextNavigation = useNextLayoutNavigation(
    repository,
    selectedGame,
    uniqueSequenceNumber,
    exactMatching.signature,
    handleLoadNextLayout,
  );
  const targetPeaks =
    targetForecast.state.status === 'ready' &&
    targetForecast.state.result !== null
      ? targetForecast.state.result.positiveLocalPeaks
      : EMPTY_TARGET_PEAKS;
  const targetReady = targetForecast.state.status === 'ready';
  const suggestion =
    prefixMatching.status === 'ready' &&
    prefixMatching.suggestion !== null &&
    prefixMatching.suggestion.cells.length > enteredCount &&
    prefixMatching.signaturePrefix !== state.rejectedSuggestionPrefix
      ? prefixMatching.suggestion
      : null;

  const handleSelectGame = (gameId: string) => {
    const game = games.find((candidate) => candidate.id === gameId);
    if (game !== undefined) {
      dispatch({
        columns: game.columns,
        gameId: game.id,
        rows: game.rows,
        type: 'select_game',
      });
    }
  };

  const updateScrollToTopVisibility = useCallback(
    (scrollOffset: number, resultsStartY: number | null) => {
      const shouldShow =
        targetReady && resultsStartY !== null && scrollOffset >= resultsStartY;
      setShowScrollToTop((current) =>
        current === shouldShow ? current : shouldShow,
      );
    },
    [targetReady],
  );

  const handleTargetResultsLayout = useCallback(
    (event: LayoutChangeEvent) => {
      const resultsStartY = event.nativeEvent.layout.y;
      setTargetResultsStartY(resultsStartY);
      updateScrollToTopVisibility(latestScrollOffsetRef.current, resultsStartY);
    },
    [updateScrollToTopVisibility],
  );

  const handleResultsScroll = useCallback(
    (event: NativeSyntheticEvent<NativeScrollEvent>) => {
      const scrollOffset = event.nativeEvent.contentOffset.y;
      latestScrollOffsetRef.current = scrollOffset;
      updateScrollToTopVisibility(scrollOffset, targetResultsStartY);
    },
    [targetResultsStartY, updateScrollToTopVisibility],
  );

  const handleScrollToTop = useCallback(() => {
    targetResultsListRef.current?.scrollToOffset({
      animated: true,
      offset: 0,
    });
    setShowScrollToTop(false);
  }, []);

  return (
    <SafeAreaView style={styles.safeArea}>
      <FlatList
        contentContainerStyle={styles.content}
        data={targetPeaks}
        initialNumToRender={8}
        keyExtractor={targetPeakKey}
        ListEmptyComponent={targetReady ? TargetResultsEmpty : null}
        ListFooterComponent={ResultsListFooter}
        ListHeaderComponent={() => (
          <View testID="workspace-list-header">
            <GameHeader
              canNext={
                uniqueSequenceNumber !== null &&
                nextNavigation.state.status !== 'loading'
              }
              canUndo={canUndo(state)}
              games={games}
              nextLoading={nextNavigation.state.status === 'loading'}
              onNext={nextNavigation.navigate}
              onReset={() => dispatch({ type: 'reset' })}
              onSelectGame={handleSelectGame}
              onUndo={() => dispatch({ type: 'undo' })}
              releaseVersion={diagnostics.releaseVersion}
              selectedGameId={state.selectedGameId}
            />

            {nextNavigation.state.status === 'error' ? (
              <View
                accessibilityLiveRegion="assertive"
                style={styles.nextError}
                testID="next-error"
              >
                <Text style={styles.nextErrorCode}>
                  {nextNavigation.state.error.code}
                </Text>
                <Text style={styles.nextErrorText}>
                  {nextNavigation.state.error.message}
                </Text>
              </View>
            ) : null}

            {selectedGame === null ? (
              <View style={styles.emptyCard}>
                <Text style={styles.emptyTitle}>Brak konfiguracji gry</Text>
                <Text style={styles.emptyText}>
                  Snapshot nie zawiera gry możliwej do wybrania.
                </Text>
              </View>
            ) : (
              <>
                <View style={styles.boardSection}>
                  <BoardGrid
                    cells={state.cells}
                    columns={state.columns}
                    rows={state.rows}
                    symbols={selectedGame.symbols}
                  />
                </View>

                <View style={styles.selectionSection}>
                  <SymbolSelection
                    disabled={boardFull || prefixMatching.status === 'error'}
                    onSelectSymbol={(mobileCode) =>
                      dispatch({ mobileCode, type: 'append_symbol' })
                    }
                    symbols={selectedGame.symbols}
                  />
                </View>

                <View style={styles.targetLimitSection}>
                  <TargetScanLimitInput
                    onChangeText={setTargetScanLimitDraft}
                    value={targetScanLimitDraft}
                  />
                </View>

                <View style={styles.section}>
                  {boardFull ? (
                    <ResultSummaryCard
                      exactState={exactMatching}
                      onRetryTarget={targetForecast.retry}
                      targetState={targetForecast.state}
                    />
                  ) : (
                    <PrefixStatus state={prefixMatching} />
                  )}
                </View>
              </>
            )}

            {targetReady ? (
              <View
                onLayout={handleTargetResultsLayout}
                testID="target-results-anchor"
              >
                <TargetResultsHeader peakCount={targetPeaks.length} />
              </View>
            ) : null}
          </View>
        )}
        maxToRenderPerBatch={8}
        onScroll={handleResultsScroll}
        ref={targetResultsListRef}
        removeClippedSubviews
        renderItem={({ item }) => <TargetPeakRow peak={item} />}
        scrollEventThrottle={16}
        showsVerticalScrollIndicator={false}
        testID="target-results-list"
        windowSize={5}
      />
      {targetReady && showScrollToTop ? (
        <Pressable
          accessibilityHint="Przewija ekran do wyboru gry i planszy."
          accessibilityLabel="Wróć na górę"
          accessibilityRole="button"
          hitSlop={6}
          onPress={handleScrollToTop}
          style={({ pressed }) => [
            styles.scrollToTopButton,
            pressed ? styles.scrollToTopButtonPressed : null,
          ]}
          testID="scroll-to-top-button"
        >
          <Text
            accessibilityElementsHidden
            importantForAccessibility="no"
            style={styles.scrollToTopIcon}
          >
            ↑
          </Text>
        </Pressable>
      ) : null}
      {selectedGame === null ? null : (
        <CandidateLayoutModal
          game={selectedGame}
          onAccept={() => {
            if (suggestion !== null) {
              dispatch({
                cells: suggestion.cells,
                type: 'complete_board',
              });
            }
          }}
          onClose={() => {
            if (suggestion !== null) {
              dispatch({
                signaturePrefix: prefixMatching.signaturePrefix,
                type: 'reject_suggestion',
              });
            }
          }}
          suggestion={suggestion}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  boardSection: {
    marginHorizontal: 12,
    marginTop: 12,
  },
  content: {
    paddingBottom: 36,
  },
  emptyCard: {
    backgroundColor: '#3b1720',
    borderColor: '#7f1d1d',
    borderRadius: 16,
    borderWidth: 1,
    margin: 18,
    padding: 18,
  },
  emptyText: {
    color: '#fecaca',
    fontSize: 14,
    lineHeight: 21,
    marginTop: 6,
  },
  emptyTitle: {
    color: '#fff1f2',
    fontSize: 17,
    fontWeight: '800',
  },
  listFooter: {
    height: 88,
  },
  matchCard: {
    alignItems: 'center',
    backgroundColor: '#0c1d32',
    borderColor: boardColors.border,
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    minHeight: 64,
    padding: 15,
  },
  matchCount: {
    color: boardColors.primary,
    fontSize: 22,
    fontWeight: '900',
    marginLeft: 'auto',
  },
  matchErrorCard: {
    alignItems: 'flex-start',
    backgroundColor: '#3b1720',
    borderColor: '#b91c1c',
    flexDirection: 'column',
  },
  matchErrorCode: {
    color: '#fca5a5',
    fontFamily: 'monospace',
    fontSize: 13,
    fontWeight: '900',
  },
  matchErrorText: {
    color: '#fecaca',
    fontSize: 13,
    lineHeight: 19,
    marginTop: 5,
  },
  matchIdleText: {
    color: boardColors.muted,
    flex: 1,
    fontSize: 12,
    lineHeight: 18,
    marginLeft: 12,
    textAlign: 'right',
  },
  matchLoadingText: {
    color: boardColors.text,
    fontSize: 13,
    fontWeight: '700',
    marginLeft: 10,
  },
  matchReadyTitle: {
    color: boardColors.text,
    fontSize: 13,
    fontWeight: '800',
  },
  nextError: {
    backgroundColor: '#3b1720',
    borderBottomColor: '#b91c1c',
    borderBottomWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  nextErrorCode: {
    color: '#fca5a5',
    fontFamily: 'monospace',
    fontSize: 12,
    fontWeight: '900',
  },
  nextErrorText: {
    color: '#fecaca',
    fontSize: 12,
    lineHeight: 18,
    marginTop: 3,
  },
  safeArea: {
    backgroundColor: boardColors.background,
    flex: 1,
  },
  scrollToTopButton: {
    alignItems: 'center',
    backgroundColor: boardColors.primary,
    borderColor: '#bfdbfe',
    borderRadius: 26,
    borderWidth: 1,
    bottom: 16,
    elevation: 6,
    height: 52,
    justifyContent: 'center',
    position: 'absolute',
    right: 16,
    shadowColor: '#000000',
    shadowOffset: { height: 3, width: 0 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    width: 52,
    zIndex: 10,
  },
  scrollToTopButtonPressed: {
    opacity: 0.78,
  },
  scrollToTopIcon: {
    color: '#07111f',
    fontSize: 28,
    fontWeight: '900',
    lineHeight: 32,
  },
  section: {
    marginHorizontal: 18,
    marginTop: 24,
  },
  selectionSection: {
    marginHorizontal: 12,
    marginTop: 10,
  },
  targetLimitSection: {
    marginHorizontal: 12,
    marginTop: 10,
  },
});
