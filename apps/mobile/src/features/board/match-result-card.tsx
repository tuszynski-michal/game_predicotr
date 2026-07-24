import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { boardColors } from './board-theme';
import type { ExactMatchingState } from './use-exact-matching';

type Props = {
  state: ExactMatchingState;
};

export function MatchResultCard({ state }: Props) {
  if (state.status === 'loading') {
    return (
      <View
        accessibilityLiveRegion="polite"
        style={styles.card}
        testID="exact-loading"
      >
        <ActivityIndicator color={boardColors.primary} size="small" />
        <Text style={styles.loadingText}>Wyszukiwanie dokładnego układu…</Text>
      </View>
    );
  }

  if (state.status === 'error') {
    return (
      <View
        accessibilityLiveRegion="assertive"
        style={[styles.card, styles.errorCard]}
        testID="exact-error"
      >
        <Text style={styles.errorCode}>{state.error.code}</Text>
        <Text style={styles.errorText}>{state.error.message}</Text>
        <Text style={styles.instruction}>
          Cofnij ostatni symbol albo wyczyść layout i spróbuj ponownie.
        </Text>
      </View>
    );
  }

  if (state.status !== 'ready' || state.result === null) {
    return (
      <View style={styles.card} testID="exact-idle">
        <Text style={styles.title}>Wynik dopasowania</Text>
        <Text style={styles.muted}>
          Uzupełnij wszystkie pola, aby wyszukać layout.
        </Text>
      </View>
    );
  }

  const result = state.result;

  if (result.status === 'unique') {
    return (
      <View
        accessibilityLiveRegion="polite"
        style={[styles.card, styles.successCard]}
        testID="exact-unique"
      >
        <Text style={styles.successTitle}>Układ znaleziony</Text>
        <Text style={styles.sequenceNumber}>
          Układ: {result.candidate.sequenceNumber}
        </Text>
        <Text style={styles.muted}>
          Jednoznaczny układ uruchamia pełny cykl Target.
        </Text>
      </View>
    );
  }

  if (result.status === 'duplicate') {
    return (
      <View
        accessibilityLiveRegion="assertive"
        style={[styles.card, styles.warningCard]}
        testID="exact-duplicate"
      >
        <Text style={styles.warningTitle}>Duplikat layoutu</Text>
        <Text style={styles.detail}>
          Liczba wystąpień: {result.occurrenceCount}
        </Text>
        <Text style={styles.detail}>
          {result.sequenceNumbers === null
            ? 'Lista pozycji przekracza limit diagnostyczny.'
            : `Pozycje: ${result.sequenceNumbers.join(', ')}`}
        </Text>
        <Text style={styles.instruction}>
          Wyczyść layout, przejdź do następnego układu źródłowego i wprowadź go
          ponownie. Target nie zostanie uruchomiony.
        </Text>
      </View>
    );
  }

  return (
    <View
      accessibilityLiveRegion="assertive"
      style={[styles.card, styles.warningCard]}
      testID="exact-not-found"
    >
      <Text style={styles.warningTitle}>Nie znaleziono layoutu</Text>
      <Text style={styles.instruction}>
        Sprawdź symbole lub cofnij ostatnią operację. Wprowadzony layout
        pozostaje na planszy.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    alignItems: 'flex-start',
    backgroundColor: '#0c1d32',
    borderColor: boardColors.border,
    borderRadius: 16,
    borderWidth: 1,
    minHeight: 72,
    padding: 15,
  },
  detail: {
    color: boardColors.text,
    fontSize: 13,
    lineHeight: 20,
    marginTop: 4,
  },
  errorCard: {
    backgroundColor: '#3b1720',
    borderColor: '#b91c1c',
  },
  errorCode: {
    color: '#fca5a5',
    fontFamily: 'monospace',
    fontSize: 13,
    fontWeight: '900',
  },
  errorText: {
    color: '#fecaca',
    fontSize: 13,
    lineHeight: 19,
    marginTop: 5,
  },
  instruction: {
    color: boardColors.muted,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 9,
  },
  loadingText: {
    color: boardColors.text,
    fontSize: 13,
    fontWeight: '700',
    marginTop: 9,
  },
  muted: {
    color: boardColors.muted,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 7,
  },
  sequenceNumber: {
    color: boardColors.text,
    fontSize: 22,
    fontWeight: '900',
    marginTop: 5,
  },
  successCard: {
    backgroundColor: '#0d2f26',
    borderColor: '#15803d',
  },
  successTitle: {
    color: '#86efac',
    fontSize: 15,
    fontWeight: '900',
  },
  title: {
    color: boardColors.text,
    fontSize: 14,
    fontWeight: '800',
  },
  warningCard: {
    backgroundColor: '#35240d',
    borderColor: '#b45309',
  },
  warningTitle: {
    color: '#fcd34d',
    fontSize: 15,
    fontWeight: '900',
  },
});
