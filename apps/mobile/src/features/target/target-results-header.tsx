import { StyleSheet, Text, View } from 'react-native';

import { boardColors } from '@/features/board/board-theme';

type Props = {
  peakCount: number;
};

export function TargetResultsHeader({ peakCount }: Props) {
  return (
    <View style={styles.container} testID="target-results-header">
      <Text accessibilityRole="header" style={styles.heading}>
        Wyniki Target
      </Text>
      <Text style={styles.description}>
        {peakCount === 1
          ? '1 dodatni lokalny szczyt'
          : `${peakCount} dodatnich lokalnych maksimów`}
        {' · '}kolejność rosnąca według numeru spinu
      </Text>
    </View>
  );
}

export function TargetResultsEmpty() {
  return (
    <View
      accessibilityLiveRegion="polite"
      style={styles.emptyCard}
      testID="target-results-empty"
    >
      <Text style={styles.emptyTitle}>Brak dodatnich lokalnych maksimów</Text>
      <Text style={styles.emptyText}>
        Pełny cykl został oceniony, ale żaden lokalny szczyt nie miał wyniku
        netto większego od zera.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 18,
    marginTop: 28,
  },
  description: {
    color: boardColors.muted,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 5,
  },
  emptyCard: {
    backgroundColor: '#0c1d32',
    borderColor: boardColors.border,
    borderRadius: 16,
    borderWidth: 1,
    marginHorizontal: 18,
    marginTop: 10,
    padding: 16,
  },
  emptyText: {
    color: boardColors.muted,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 5,
  },
  emptyTitle: {
    color: boardColors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  heading: {
    color: boardColors.text,
    fontSize: 20,
    fontWeight: '900',
  },
});
