import { useReducer } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type { LocalGameConfig } from '@/data/local-layout-repository';
import { TargetSummaryCard } from '@/features/target/target-summary-card';
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
import { MatchResultCard } from './match-result-card';
import { SymbolSelection } from './symbol-selection';
import {
  useExactMatching,
  type ExactMatchRepository,
} from './use-exact-matching';
import {
  usePrefixMatching,
  type PrefixMatchRepository,
  type PrefixMatchingState,
} from './use-prefix-matching';

export type MatchingRepository = ExactMatchRepository &
  PrefixMatchRepository &
  TargetForecastRepository;

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
  const [state, dispatch] = useReducer(boardReducer, games, initialState);
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
  const exactMatching = useExactMatching(repository, selectedGame, state.cells);
  const uniqueSequenceNumber =
    exactMatching.status === 'ready' &&
    exactMatching.result?.status === 'unique'
      ? exactMatching.result.candidate.sequenceNumber
      : null;
  const targetForecast = useTargetForecast(
    repository,
    selectedGame,
    uniqueSequenceNumber,
    diagnostics,
  );
  const candidate =
    prefixMatching.status === 'ready' &&
    prefixMatching.candidateCount === 1 &&
    prefixMatching.candidate !== null &&
    prefixMatching.candidate.cells.length > enteredCount &&
    prefixMatching.signaturePrefix !== state.rejectedSuggestionPrefix
      ? prefixMatching.candidate
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

  return (
    <SafeAreaView style={styles.safeArea}>
      <ScrollView
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <GameHeader
          canUndo={canUndo(state)}
          games={games}
          onReset={() => dispatch({ type: 'reset' })}
          onSelectGame={handleSelectGame}
          onUndo={() => dispatch({ type: 'undo' })}
          releaseVersion={diagnostics.releaseVersion}
          selectedGameId={state.selectedGameId}
        />

        {selectedGame === null ? (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyTitle}>Brak konfiguracji gry</Text>
            <Text style={styles.emptyText}>
              Snapshot nie zawiera gry możliwej do wybrania.
            </Text>
          </View>
        ) : (
          <>
            <View style={styles.section}>
              <View style={styles.sectionHeading}>
                <Text accessibilityRole="header" style={styles.heading}>
                  Layout
                </Text>
                <Text style={styles.progress}>
                  {enteredCount}/{state.cells.length}
                </Text>
              </View>
              <BoardGrid
                cells={state.cells}
                columns={state.columns}
                rows={state.rows}
                symbols={selectedGame.symbols}
              />
            </View>

            <View style={styles.section}>
              <SymbolSelection
                disabled={boardFull || prefixMatching.status === 'error'}
                onSelectSymbol={(mobileCode) =>
                  dispatch({ mobileCode, type: 'append_symbol' })
                }
                symbols={selectedGame.symbols}
              />
            </View>

            <View style={styles.section}>
              {boardFull ? (
                <MatchResultCard state={exactMatching} />
              ) : (
                <PrefixStatus state={prefixMatching} />
              )}
            </View>
            {uniqueSequenceNumber === null ? null : (
              <View style={styles.section}>
                <TargetSummaryCard
                  onRetry={targetForecast.retry}
                  state={targetForecast.state}
                />
              </View>
            )}
          </>
        )}

        <View style={styles.statusCard}>
          <Text style={styles.statusTitle}>Dane lokalne gotowe</Text>
          <Text style={styles.statusText}>
            {diagnostics.gameCount} gry · {diagnostics.layoutCount} layoutów ·
            schema {diagnostics.schemaVersion}
          </Text>
          <Text style={styles.statusNote}>
            Matching i pełny cykl Target działają lokalnie. Szczegółowa tabela
            wyników zostanie podłączona w następnym zadaniu.
          </Text>
        </View>
      </ScrollView>
      {selectedGame === null ? null : (
        <CandidateLayoutModal
          candidate={candidate}
          game={selectedGame}
          onAccept={() => {
            if (candidate !== null) {
              dispatch({
                cells: candidate.cells,
                type: 'complete_board',
              });
            }
          }}
          onClose={() => {
            if (candidate !== null) {
              dispatch({
                signaturePrefix: prefixMatching.signaturePrefix,
                type: 'reject_suggestion',
              });
            }
          }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
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
  heading: {
    color: boardColors.text,
    fontSize: 20,
    fontWeight: '800',
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
  progress: {
    color: boardColors.primary,
    fontSize: 14,
    fontWeight: '800',
  },
  safeArea: {
    backgroundColor: boardColors.background,
    flex: 1,
  },
  section: {
    marginHorizontal: 18,
    marginTop: 24,
  },
  sectionHeading: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 12,
  },
  statusCard: {
    backgroundColor: '#0c1d32',
    borderColor: boardColors.border,
    borderRadius: 16,
    borderWidth: 1,
    marginHorizontal: 18,
    marginTop: 26,
    padding: 16,
  },
  statusNote: {
    color: boardColors.muted,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 9,
  },
  statusText: {
    color: boardColors.muted,
    fontSize: 12,
    marginTop: 5,
  },
  statusTitle: {
    color: '#86efac',
    fontSize: 14,
    fontWeight: '800',
  },
});
