import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  LOCAL_DATA_ERROR_CODE,
  type LocalDataError,
  type SnapshotDiagnostics,
} from '@/data/bundled-snapshot';

type Props = {
  diagnostics: SnapshotDiagnostics | null;
  error: LocalDataError | null;
};

type DetailRowProps = {
  label: string;
  value: string;
};

function DetailRow({ label, value }: DetailRowProps) {
  return (
    <View style={styles.detailRow}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text selectable style={styles.detailValue}>
        {value}
      </Text>
    </View>
  );
}

export function SnapshotDiagnosticScreen({ diagnostics, error }: Props) {
  if (error !== null) {
    return (
      <SafeAreaView style={styles.errorContainer}>
        <View style={styles.errorCard}>
          <Text style={styles.eyebrow}>DANE LOKALNE</Text>
          <Text style={styles.errorCode}>{LOCAL_DATA_ERROR_CODE}</Text>
          <Text style={styles.errorMessage}>{error.message}</Text>
          <Text style={styles.errorHint}>
            Wygeneruj poprawny snapshot i zbuduj nową wersję aplikacji.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  if (diagnostics === null) {
    return (
      <SafeAreaView style={styles.loadingContainer}>
        <ActivityIndicator color="#2563eb" size="large" />
        <Text style={styles.loadingText}>Weryfikacja danych offline…</Text>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.eyebrow}>M1.1 · OFFLINE SQLITE SPIKE</Text>
        <Text style={styles.title}>Sequence Target Analyzer</Text>
        <Text style={styles.subtitle}>
          Snapshot został otwarty i zweryfikowany bez połączenia z API.
        </Text>

        <View style={styles.successBadge}>
          <View style={styles.successDot} />
          <Text style={styles.successText}>Dane lokalne gotowe</Text>
        </View>

        <View style={styles.card}>
          <DetailRow label="Release" value={diagnostics.releaseVersion} />
          <DetailRow
            label="Wersja schematu"
            value={String(diagnostics.schemaVersion)}
          />
          <DetailRow label="Algorytm" value={diagnostics.algorithmVersion} />
          <DetailRow label="Fixture" value={diagnostics.fixtureVersion} />
          <DetailRow
            label="Wersja datasetu"
            value={String(diagnostics.datasetVersion)}
          />
          <DetailRow
            label="Wersja reguł"
            value={String(diagnostics.rulesVersion)}
          />
          <DetailRow label="Gry" value={String(diagnostics.gameCount)} />
          <DetailRow label="Layouty" value={String(diagnostics.layoutCount)} />
          <DetailRow label="Lokalna baza" value={diagnostics.databaseName} />
          <DetailRow
            label="SHA-256 pliku"
            value={diagnostics.snapshotFileSha256}
          />
          <DetailRow
            label="SHA-256 treści"
            value={diagnostics.logicalContentSha256}
          />
        </View>

        <Text style={styles.footer}>
          Zmiana danych wymaga wygenerowania snapshotu i zbudowania nowego APK.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#ffffff',
    borderColor: '#dbe4f0',
    borderRadius: 20,
    borderWidth: 1,
    paddingHorizontal: 20,
  },
  container: {
    backgroundColor: '#f4f7fb',
    flex: 1,
  },
  content: {
    padding: 24,
    paddingBottom: 40,
  },
  detailLabel: {
    color: '#64748b',
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 5,
  },
  detailRow: {
    borderBottomColor: '#e8eef6',
    borderBottomWidth: 1,
    paddingVertical: 16,
  },
  detailValue: {
    color: '#0f172a',
    fontFamily: 'monospace',
    fontSize: 14,
    lineHeight: 20,
  },
  errorCard: {
    backgroundColor: '#fff7f7',
    borderColor: '#fecaca',
    borderRadius: 20,
    borderWidth: 1,
    padding: 24,
  },
  errorCode: {
    color: '#b91c1c',
    fontFamily: 'monospace',
    fontSize: 22,
    fontWeight: '700',
    marginTop: 12,
  },
  errorContainer: {
    backgroundColor: '#f4f7fb',
    flex: 1,
    justifyContent: 'center',
    padding: 24,
  },
  errorHint: {
    color: '#7f1d1d',
    fontSize: 14,
    lineHeight: 21,
    marginTop: 20,
  },
  errorMessage: {
    color: '#450a0a',
    fontSize: 16,
    lineHeight: 24,
    marginTop: 12,
  },
  eyebrow: {
    color: '#2563eb',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 1.1,
  },
  footer: {
    color: '#64748b',
    fontSize: 13,
    lineHeight: 20,
    marginTop: 20,
    textAlign: 'center',
  },
  loadingContainer: {
    alignItems: 'center',
    backgroundColor: '#f4f7fb',
    flex: 1,
    justifyContent: 'center',
  },
  loadingText: {
    color: '#475569',
    fontSize: 15,
    marginTop: 14,
  },
  subtitle: {
    color: '#475569',
    fontSize: 16,
    lineHeight: 24,
    marginBottom: 20,
    marginTop: 10,
  },
  successBadge: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: '#dcfce7',
    borderRadius: 999,
    flexDirection: 'row',
    marginBottom: 20,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  successDot: {
    backgroundColor: '#16a34a',
    borderRadius: 5,
    height: 10,
    marginRight: 8,
    width: 10,
  },
  successText: {
    color: '#166534',
    fontSize: 13,
    fontWeight: '700',
  },
  title: {
    color: '#0f172a',
    fontSize: 30,
    fontWeight: '800',
    letterSpacing: -0.7,
    marginTop: 8,
  },
});
