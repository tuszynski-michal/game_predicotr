import { SQLiteProvider, type SQLiteDatabase } from 'expo-sqlite';
import { useCallback, useState } from 'react';

import {
  asLocalDataError,
  buildLocalDatabaseName,
  readSnapshotDiagnostics,
  snapshotAssetId,
  snapshotManifest,
  type LocalDataError,
  type SnapshotDiagnostics,
} from '@/data/bundled-snapshot';

import { SnapshotDiagnosticScreen } from './snapshot-diagnostic-screen';

export function LocalSnapshotGate() {
  const [diagnostics, setDiagnostics] = useState<SnapshotDiagnostics | null>(
    null,
  );
  const [error, setError] = useState<LocalDataError | null>(null);

  const initialize = useCallback(async (database: SQLiteDatabase) => {
    const verifiedDiagnostics = await readSnapshotDiagnostics(database);
    setDiagnostics(verifiedDiagnostics);
  }, []);

  const handleError = useCallback((providerError: Error) => {
    setError(asLocalDataError(providerError));
  }, []);

  if (error !== null) {
    return <SnapshotDiagnosticScreen error={error} diagnostics={null} />;
  }

  return (
    <SQLiteProvider
      assetSource={{ assetId: snapshotAssetId }}
      databaseName={buildLocalDatabaseName(snapshotManifest)}
      onError={handleError}
      onInit={initialize}
    >
      <SnapshotDiagnosticScreen diagnostics={diagnostics} error={null} />
    </SQLiteProvider>
  );
}
