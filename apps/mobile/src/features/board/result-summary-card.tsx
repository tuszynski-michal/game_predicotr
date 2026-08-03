import { useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { TargetForecastState } from '@/features/target/use-target-forecast';

import { boardColors } from './board-theme';
import type { ExactMatchingState } from './use-exact-matching';

type Props = {
  exactState: ExactMatchingState;
  onRetryTarget: () => void;
  targetState: TargetForecastState;
};

type SummaryValueProps = {
  label: string;
  testID: string;
  value: number;
};

function SummaryValue({ label, testID, value }: SummaryValueProps) {
  return (
    <View style={styles.summaryItem} testID={testID}>
      <Text style={styles.summaryLabel}>{label}</Text>
      <Text style={styles.summaryValue}>{value}</Text>
    </View>
  );
}

export function ResultSummaryCard({
  exactState,
  onRetryTarget,
  targetState,
}: Props) {
  const [detailsExpanded, setDetailsExpanded] = useState(false);

  if (exactState.status === 'loading') {
    return (
      <View
        accessibilityLiveRegion="polite"
        style={styles.card}
        testID="result-summary"
      >
        <View style={styles.loadingRow}>
          <ActivityIndicator color={boardColors.primary} size="small" />
          <Text style={styles.loadingText} testID="result-status-loading">
            Wyszukiwanie układu…
          </Text>
        </View>
      </View>
    );
  }

  if (exactState.status === 'error') {
    return (
      <View
        accessibilityLiveRegion="assertive"
        style={[styles.card, styles.errorCard]}
        testID="result-summary"
      >
        <Text style={styles.errorTitle} testID="result-status-error">
          Błąd danych lokalnych
        </Text>
        <Text style={styles.errorCode}>{exactState.error.code}</Text>
        <Text style={styles.errorText}>{exactState.error.message}</Text>
        <Text style={styles.instruction}>
          Cofnij ostatni symbol albo wyczyść layout i spróbuj ponownie.
        </Text>
      </View>
    );
  }

  if (exactState.status !== 'ready' || exactState.result === null) {
    return (
      <View style={styles.card} testID="result-summary">
        <Text style={styles.neutralTitle}>Wynik dopasowania</Text>
        <Text style={styles.muted}>
          Uzupełnij wszystkie pola, aby wyszukać layout.
        </Text>
      </View>
    );
  }

  const exactResult = exactState.result;
  if (exactResult.status === 'duplicate') {
    return (
      <View
        accessibilityLiveRegion="assertive"
        style={[styles.card, styles.warningCard]}
        testID="result-summary"
      >
        <Text style={styles.warningTitle} testID="result-status-duplicate">
          Duplikat layoutu
        </Text>
        <Text style={styles.detail}>
          Liczba wystąpień: {exactResult.occurrenceCount}
        </Text>
        <Text style={styles.detail}>
          {exactResult.sequenceNumbers === null
            ? 'Lista pozycji przekracza limit diagnostyczny.'
            : `Pozycje: ${exactResult.sequenceNumbers.join(', ')}`}
        </Text>
        <Text style={styles.instruction}>
          Wyczyść layout, przejdź do następnego układu źródłowego i wprowadź go
          ponownie. Target nie zostanie uruchomiony.
        </Text>
      </View>
    );
  }

  if (exactResult.status === 'not_found') {
    return (
      <View
        accessibilityLiveRegion="assertive"
        style={[styles.card, styles.errorCard]}
        testID="result-summary"
      >
        <Text style={styles.errorTitle} testID="result-status-not-found">
          Nie znaleziono layoutu
        </Text>
        <Text style={styles.instruction}>
          Sprawdź symbole lub cofnij ostatnią operację. Wprowadzony layout
          pozostaje na planszy.
        </Text>
      </View>
    );
  }

  const sequenceNumber = exactResult.candidate.sequenceNumber;

  if (targetState.status === 'loading') {
    return (
      <View
        accessibilityLiveRegion="polite"
        style={styles.card}
        testID="result-summary"
      >
        <Text style={styles.neutralTitle}>Układ znaleziony</Text>
        <Text style={styles.sequenceNumber}>Układ: {sequenceNumber}</Text>
        <View style={styles.loadingRow}>
          <ActivityIndicator color={boardColors.primary} size="small" />
          <Text style={styles.loadingText} testID="result-status-loading">
            Obliczanie Target…
          </Text>
        </View>
      </View>
    );
  }

  if (targetState.status === 'error') {
    return (
      <View
        accessibilityLiveRegion="assertive"
        style={[styles.card, styles.errorCard]}
        testID="result-summary"
      >
        <Text style={styles.errorTitle} testID="result-status-error">
          Nie udało się obliczyć układu
        </Text>
        <Text style={styles.sequenceNumber}>Układ: {sequenceNumber}</Text>
        <Text style={styles.errorCode}>{targetState.error.code}</Text>
        <Text style={styles.errorText}>{targetState.error.message}</Text>
        <Pressable
          accessibilityLabel="Ponów obliczenie Target"
          accessibilityRole="button"
          onPress={onRetryTarget}
          style={({ pressed }) => [
            styles.retryButton,
            pressed && styles.retryButtonPressed,
          ]}
          testID="target-retry-button"
        >
          <Text style={styles.retryText}>Ponów obliczenie</Text>
        </Pressable>
      </View>
    );
  }

  if (targetState.status !== 'ready' || targetState.result === null) {
    return (
      <View
        accessibilityLiveRegion="polite"
        style={styles.card}
        testID="result-summary"
      >
        <Text style={styles.neutralTitle} testID="result-status-pending">
          Układ znaleziony
        </Text>
        <Text style={styles.sequenceNumber}>Układ: {sequenceNumber}</Text>
        <Text style={styles.muted}>
          Ustaw poprawny zakres Targetu, aby obliczyć wynik.
        </Text>
      </View>
    );
  }

  const targetResult = targetState.result;
  return (
    <View
      accessibilityLiveRegion="polite"
      style={[styles.card, styles.successCard]}
      testID="result-summary"
    >
      <Text style={styles.successTitle} testID="result-status-success">
        Układ znaleziony i obliczony
      </Text>
      <Text style={styles.sequenceNumber}>Układ: {sequenceNumber}</Text>
      <Pressable
        accessibilityLabel={
          detailsExpanded ? 'Ukryj szczegóły wyniku' : 'Pokaż szczegóły wyniku'
        }
        accessibilityRole="button"
        accessibilityState={{ expanded: detailsExpanded }}
        onPress={() => setDetailsExpanded((expanded) => !expanded)}
        style={({ pressed }) => [
          styles.detailsButton,
          pressed && styles.detailsButtonPressed,
        ]}
        testID="result-details-toggle"
      >
        <Text style={styles.detailsButtonText}>
          {detailsExpanded ? 'Ukryj szczegóły' : 'Szczegóły'}
        </Text>
      </Pressable>
      {detailsExpanded ? (
        <View style={styles.summaryGrid} testID="result-details">
          <SummaryValue
            label="Koszt spinu"
            testID="target-spin-cost"
            value={targetResult.spinCost}
          />
          <SummaryValue
            label="Koszt"
            testID="target-final-cost"
            value={targetResult.finalCumulativeCost}
          />
          <SummaryValue
            label="Suma końcowa"
            testID="target-final-net"
            value={targetResult.finalNetCredits}
          />
        </View>
      ) : null}
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
  detailsButton: {
    alignItems: 'center',
    alignSelf: 'stretch',
    borderColor: '#15803d',
    borderRadius: 10,
    borderWidth: 1,
    justifyContent: 'center',
    marginTop: 10,
    minHeight: 44,
    paddingHorizontal: 12,
  },
  detailsButtonPressed: {
    backgroundColor: '#17483b',
  },
  detailsButtonText: {
    color: '#bbf7d0',
    fontSize: 13,
    fontWeight: '800',
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
    marginTop: 5,
  },
  errorText: {
    color: '#fecaca',
    fontSize: 13,
    lineHeight: 19,
    marginTop: 5,
  },
  errorTitle: {
    color: '#fff1f2',
    fontSize: 15,
    fontWeight: '900',
  },
  instruction: {
    color: boardColors.muted,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 9,
  },
  loadingRow: {
    alignItems: 'center',
    flexDirection: 'row',
    marginTop: 9,
  },
  loadingText: {
    color: boardColors.text,
    fontSize: 13,
    fontWeight: '700',
    marginLeft: 9,
  },
  muted: {
    color: boardColors.muted,
    fontSize: 12,
    lineHeight: 18,
    marginTop: 7,
  },
  neutralTitle: {
    color: boardColors.text,
    fontSize: 15,
    fontWeight: '900',
  },
  retryButton: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: '#7f1d1d',
    borderColor: '#fca5a5',
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: 'center',
    marginTop: 14,
    minHeight: 48,
    paddingHorizontal: 16,
  },
  retryButtonPressed: {
    backgroundColor: '#991b1b',
  },
  retryText: {
    color: '#fff1f2',
    fontSize: 14,
    fontWeight: '900',
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
  summaryGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 8,
    width: '100%',
  },
  summaryItem: {
    backgroundColor: '#0b241e',
    borderRadius: 10,
    flexBasis: '30%',
    flexGrow: 1,
    minWidth: 88,
    padding: 9,
  },
  summaryLabel: {
    color: boardColors.muted,
    fontSize: 11,
  },
  summaryValue: {
    color: boardColors.text,
    fontSize: 18,
    fontWeight: '900',
    marginTop: 3,
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
