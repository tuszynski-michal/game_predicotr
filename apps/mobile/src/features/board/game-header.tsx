import type { LocalGameConfig } from '@/data/local-layout-repository';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { boardColors } from './board-theme';

type Props = {
  canNext: boolean;
  canUndo: boolean;
  games: readonly LocalGameConfig[];
  nextLoading?: boolean;
  onNext?: () => void;
  onReset: () => void;
  onSelectGame: (gameId: string) => void;
  onUndo: () => void;
  releaseVersion: string;
  selectedGameId: string | null;
};

export function GameHeader({
  canNext,
  canUndo,
  games,
  nextLoading = false,
  onNext,
  onReset,
  onSelectGame,
  onUndo,
  releaseVersion,
  selectedGameId,
}: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.version} testID="release-version">
        ver {releaseVersion}
      </Text>

      <Text style={styles.label}>Gra</Text>
      <ScrollView
        contentContainerStyle={styles.gameList}
        horizontal
        showsHorizontalScrollIndicator={false}
      >
        {games.map((game) => {
          const selected = game.id === selectedGameId;
          return (
            <Pressable
              accessibilityLabel={`Wybierz grę ${game.name}`}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              key={game.id}
              onPress={() => onSelectGame(game.id)}
              style={({ pressed }) => [
                styles.gameButton,
                selected && styles.gameButtonSelected,
                pressed && !selected && styles.gameButtonPressed,
              ]}
              testID={`game-option-${game.id}`}
            >
              <Text
                style={[
                  styles.gameButtonText,
                  selected && styles.gameButtonTextSelected,
                ]}
              >
                {game.name}
              </Text>
              <Text
                style={[styles.gameMeta, selected && styles.gameMetaSelected]}
              >
                {game.rows} × {game.columns}
              </Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <View style={styles.actions} testID="header-actions">
        <Pressable
          accessibilityHint="Ładuje dokładny kolejny rekord cyklicznej sekwencji."
          accessibilityLabel="Przejdź do następnego layoutu"
          accessibilityRole="button"
          accessibilityState={{ busy: nextLoading, disabled: !canNext }}
          disabled={!canNext}
          onPress={onNext}
          style={({ pressed }) => [
            styles.actionButton,
            !canNext && styles.actionButtonDisabled,
            pressed && canNext && styles.actionButtonPressed,
          ]}
          testID="next-button"
        >
          {nextLoading ? (
            <ActivityIndicator
              color={boardColors.primary}
              size="small"
              testID="next-loading"
            />
          ) : (
            <Text
              style={[styles.actionText, !canNext && styles.actionTextDisabled]}
            >
              Next
            </Text>
          )}
        </Pressable>
        <Pressable
          accessibilityLabel="Cofnij ostatnią operację"
          accessibilityRole="button"
          accessibilityState={{ disabled: !canUndo }}
          disabled={!canUndo}
          onPress={onUndo}
          style={({ pressed }) => [
            styles.actionButton,
            !canUndo && styles.actionButtonDisabled,
            pressed && canUndo && styles.actionButtonPressed,
          ]}
          testID="undo-button"
        >
          <Text
            style={[styles.actionText, !canUndo && styles.actionTextDisabled]}
          >
            Undo
          </Text>
        </Pressable>
        <Pressable
          accessibilityLabel="Wyczyść planszę"
          accessibilityRole="button"
          onPress={onReset}
          style={({ pressed }) => [
            styles.actionButton,
            pressed && styles.actionButtonPressed,
          ]}
          testID="reset-button"
        >
          <Text style={styles.actionText}>Reset</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  actionButton: {
    alignItems: 'center',
    borderColor: boardColors.border,
    borderRadius: 12,
    borderWidth: 1,
    flex: 1,
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: 10,
  },
  actionButtonDisabled: {
    opacity: 0.45,
  },
  actionButtonPressed: {
    backgroundColor: '#1c3654',
  },
  actionText: {
    color: boardColors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  actionTextDisabled: {
    color: boardColors.muted,
  },
  actions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  container: {
    backgroundColor: boardColors.card,
    borderBottomColor: boardColors.border,
    borderBottomWidth: 1,
    paddingBottom: 12,
    paddingHorizontal: 12,
    paddingTop: 8,
  },
  gameButton: {
    backgroundColor: '#182f4b',
    borderColor: boardColors.border,
    borderRadius: 12,
    borderWidth: 1,
    minHeight: 52,
    minWidth: 104,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  gameButtonPressed: {
    backgroundColor: '#203c5e',
  },
  gameButtonSelected: {
    backgroundColor: boardColors.primary,
    borderColor: boardColors.primary,
  },
  gameButtonText: {
    color: boardColors.text,
    fontSize: 14,
    fontWeight: '700',
  },
  gameButtonTextSelected: {
    color: boardColors.textDark,
  },
  gameList: {
    gap: 8,
    paddingRight: 12,
  },
  gameMeta: {
    color: boardColors.muted,
    fontSize: 11,
    marginTop: 2,
  },
  gameMetaSelected: {
    color: '#164e63',
  },
  label: {
    color: boardColors.muted,
    fontSize: 11,
    fontWeight: '700',
    marginBottom: 6,
    marginTop: 8,
    textTransform: 'uppercase',
  },
  version: {
    color: boardColors.primary,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.4,
  },
});
