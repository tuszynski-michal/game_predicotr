import type { LocalGameConfig } from '@/data/local-layout-repository';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { boardColors } from './board-theme';

type Props = {
  canUndo: boolean;
  games: readonly LocalGameConfig[];
  onReset: () => void;
  onSelectGame: (gameId: string) => void;
  onUndo: () => void;
  releaseVersion: string;
  selectedGameId: string | null;
};

export function GameHeader({
  canUndo,
  games,
  onReset,
  onSelectGame,
  onUndo,
  releaseVersion,
  selectedGameId,
}: Props) {
  return (
    <View style={styles.container}>
      <View style={styles.titleRow}>
        <View style={styles.titleBlock}>
          <Text style={styles.eyebrow}>OFFLINE · {releaseVersion}</Text>
          <Text accessibilityRole="header" style={styles.title}>
            Sequence Target
          </Text>
        </View>
        <View style={styles.actions}>
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
    </View>
  );
}

const styles = StyleSheet.create({
  actionButton: {
    alignItems: 'center',
    borderColor: boardColors.border,
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 44,
    minWidth: 68,
    paddingHorizontal: 12,
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
  },
  container: {
    backgroundColor: boardColors.card,
    borderBottomColor: boardColors.border,
    borderBottomWidth: 1,
    paddingBottom: 18,
    paddingHorizontal: 18,
    paddingTop: 12,
  },
  eyebrow: {
    color: boardColors.primary,
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 0.9,
  },
  gameButton: {
    backgroundColor: '#182f4b',
    borderColor: boardColors.border,
    borderRadius: 14,
    borderWidth: 1,
    minHeight: 58,
    minWidth: 110,
    paddingHorizontal: 14,
    paddingVertical: 9,
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
    gap: 10,
    paddingRight: 18,
  },
  gameMeta: {
    color: boardColors.muted,
    fontSize: 11,
    marginTop: 3,
  },
  gameMetaSelected: {
    color: '#164e63',
  },
  label: {
    color: boardColors.muted,
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 8,
    marginTop: 18,
    textTransform: 'uppercase',
  },
  title: {
    color: boardColors.text,
    fontSize: 24,
    fontWeight: '800',
    letterSpacing: -0.5,
    marginTop: 3,
  },
  titleBlock: {
    flex: 1,
    marginRight: 12,
  },
  titleRow: {
    alignItems: 'center',
    flexDirection: 'row',
  },
});
