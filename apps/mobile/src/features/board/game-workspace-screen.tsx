import { useReducer } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import type { SnapshotDiagnostics } from '@/data/bundled-snapshot';
import type { LocalGameConfig } from '@/data/local-layout-repository';

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
import { GameHeader } from './game-header';
import { SymbolSelection } from './symbol-selection';

type Props = {
  diagnostics: SnapshotDiagnostics;
  games: readonly LocalGameConfig[];
};

function initialState(games: readonly LocalGameConfig[]): BoardState {
  const firstGame = games[0];
  return firstGame === undefined
    ? createEmptyBoardState()
    : createBoardState(firstGame.id, firstGame.rows, firstGame.columns);
}

export function GameWorkspaceScreen({ diagnostics, games }: Props) {
  const [state, dispatch] = useReducer(boardReducer, games, initialState);
  const selectedGame =
    games.find((game) => game.id === state.selectedGameId) ?? null;
  const enteredCount = enteredCellCount(state);

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
                disabled={isBoardFull(state)}
                onSelectSymbol={(mobileCode) =>
                  dispatch({ mobileCode, type: 'append_symbol' })
                }
                symbols={selectedGame.symbols}
              />
            </View>
          </>
        )}

        <View style={styles.statusCard}>
          <Text style={styles.statusTitle}>Dane lokalne gotowe</Text>
          <Text style={styles.statusText}>
            {diagnostics.gameCount} gry · {diagnostics.layoutCount} layoutów ·
            schema {diagnostics.schemaVersion}
          </Text>
          <Text style={styles.statusNote}>
            Matching prefix zostanie podłączony w następnym zadaniu.
          </Text>
        </View>
      </ScrollView>
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
